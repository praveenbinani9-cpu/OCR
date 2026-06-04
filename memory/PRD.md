# DocExtract AI — PRD

## Original problem statement
Production-grade document intelligence SaaS API for Indian GST documents.
Stack: Python 3.11, FastAPI 0.111, SQLAlchemy 2.0, PostgreSQL, Redis, Celery 5.4,
MinIO (S3), Google Gemini Flash (`gemini-2.0-flash`), PaddleOCR + pytesseract,
Docker Compose, Kubernetes (HPA / PDB / ResourceQuota).

## User choices (verbatim)
- Stack: option (a) — generate full production code as specified.
- LLM: **Google Gemini Flash** via direct `google-generativeai` SDK
  (switched 2026-02-05 from earlier Claude-based stack — see history).
- OCR: pytesseract primary, PaddleOCR via `OCR_ENGINE=paddle` feature flag with
  automatic fallback on failure.
- Frontend: None — backend + Postman collection only.

## Architecture (current)
```
client → nginx (TLS, per-IP rate-limit) → FastAPI api (uvicorn x4)
                                            ├── PostgreSQL (multi-tenant)
                                            ├── Redis (cache + Celery broker)
                                            ├── MinIO (raw file storage)
                                            └── Celery worker (4 concurrency)
                                                  ├── OCR (Paddle/Tesseract + OpenCV)
                                                  ├── LLM extraction (Gemini Flash)
                                                  └── webhook (HMAC-SHA256 signed)
```

## What's implemented
- 88 files under `/app/docextract-ai/` (was 83 — added webhook_delivery model,
  prompt specialization, validation simplification, Gemini migration).
- Models: tenants (with `webhook_secret`), users, documents, extractions,
  review_queue, audit_logs, api_keys (with `revoked_at`), webhook_deliveries.
  Cross-dialect `GUID` + `JSONType` (Postgres-native, SQLite-friendly).
- API endpoints (all under `/api/v1`):
  - `POST  /auth/token`, `POST /auth/api-key`
  - `GET   /auth/api-keys`, `POST /auth/api-keys/{id}/rotate`, `DELETE /auth/api-keys/{id}`
  - `POST  /extract` (multipart, sync + async via Celery, webhook_url)
  - `GET   /documents` (paginated), `GET /documents/{id}`
  - `GET   /review-queue`, `PATCH /review-queue/{id}`
  - `GET   /tenants/usage`
  - `GET   /tenants/webhook-secret`, `POST /tenants/webhook-secret/rotate`,
    `DELETE /tenants/webhook-secret`
  - `GET   /webhook-deliveries?document_id={id}` (delivery debug log)
  - `GET   /health`, `GET /metrics`
- Auth: JWT + API key (soft-revokable). Cross-tenant queries forbidden by design.
- LLM: Google Gemini Flash via `google.generativeai`. System instruction =
  `SYSTEM_PROMPT`, `temperature=0`, `max_output_tokens=4096`,
  `response_mime_type=application/json`. Per-document-type prompt specialization
  for EWAY_BILL / DELIVERY_CHALLAN / TAX_INVOICE.
- Validation (minimal, no external calls):
  - `gstin_valid` — 15-char length only
  - `amounts_reconciled` — subtotal + tax ≈ grand_total (±1)
  - `duplicate_detected` — DB lookup on (tenant, doc_no, vendor_gstin, date)
- Storage: S3/MinIO via boto3, SSE-AES256.
- Webhooks: Stripe-style HMAC-SHA256 signing (`X-DocExtract-Signature: t=…,v1=…`),
  per-attempt logging in `webhook_deliveries`, helper `verify_signature()`.
- Celery: 4 concurrency, prefetch 1, ack_late, queues `document_processing` /
  `notifications`, daily cleanup beat at 03:00 UTC.
- Observability: structlog JSON, Prometheus histograms, Sentry hook, audit
  middleware on mutating requests.
- Rate limiting: slowapi, Redis backend (memory in tests).

## Verification (last run)
- `pytest -q` → **63 passed** (1 SDK deprecation warning, see note below)
- `ruff` lint → clean
- `python -c "from app.main import app"` → 21 routes registered
- No anthropic / claude / emergent references anywhere in the codebase.

> **Note on `google-generativeai`**: Google has deprecated this package in
> favour of the newer `google-genai`. The current implementation uses
> `google-generativeai>=0.8.0` per explicit user spec; surfaces a one-line
> `FutureWarning` but functions normally.

## History

### 2026-02-05 — Migrated LLM from Anthropic Claude → Google Gemini Flash
- `requirements.txt`: removed `anthropic==0.28.0` and `emergentintegrations`;
  added `google-generativeai>=0.8.0`.
- `app/core/config.py`: dropped `anthropic_api_key`, `emergent_llm_key`,
  `llm_provider`. Added `gemini_api_key`. `llm_model` default now
  `gemini-2.0-flash`.
- `app/services/extraction.py`: replaced dual Emergent / Anthropic SDK paths
  with a single `google.generativeai` call. `system_instruction=SYSTEM_PROMPT`,
  `temperature=0`, `max_output_tokens=4096`, `response_mime_type=application/json`.
  Sync SDK wrapped in `asyncio.to_thread` to preserve the async interface.
  Tenacity retry, JSON envelope stripping, and the self-correction pass are all
  unchanged.
- `.env.example`: `ANTHROPIC_API_KEY` / `EMERGENT_LLM_KEY` / `LLM_PROVIDER` →
  `GEMINI_API_KEY=your-gemini-key-here` + `LLM_MODEL=gemini-2.0-flash`.
- `docker-compose.yml`: api + worker now pass through
  `GEMINI_API_KEY: ${GEMINI_API_KEY}` and `LLM_MODEL: ${LLM_MODEL:-gemini-2.0-flash}`.
- `k8s/configmap.yaml`: dropped `LLM_PROVIDER`, set `LLM_MODEL: gemini-2.0-flash`.
- `k8s/secrets.yaml`: dropped `ANTHROPIC_API_KEY` / `EMERGENT_LLM_KEY`, added
  `GEMINI_API_KEY`.
- `README.md`: updated stack description, quick-start, and architecture diagram.
  Added "Get a free key at aistudio.google.com" instruction.
- `app/prompts/extraction.py`: only wording change — "help Claude" → "help the LLM".
  All prompt templates, schema hints, and per-type specialization blocks unchanged.
- `tests/conftest.py`: `EMERGENT_LLM_KEY` → `GEMINI_API_KEY` test env var.
- All other test files unchanged — `tests/unit/test_extraction_service.py` patches
  `ExtractionService._llm_call` directly so it's provider-agnostic and required
  zero changes.
- All 63 tests pass after migration.

### 2026-02-04 — Validation simplified to 3 checks (no external calls)
Kept: gstin 15-char length, amounts_reconciled, duplicate_detected.
Removed: `date_valid`, `tax_reconciled`, GSTIN structural regex, `parse_date`.

### 2026-02-03 — webhook_deliveries log + per-document-type prompt specialization
Added `WebhookDelivery` model, `GET /webhook-deliveries?document_id=…`,
EWAY_BILL / DELIVERY_CHALLAN / TAX_INVOICE prompt blocks + keyword detector.

### 2026-02-02 — Webhook HMAC verification + API-key lifecycle
Stripe-style `X-DocExtract-Signature: t=…,v1=…`, `verify_signature()` helper,
GET/POST/DELETE for `/auth/api-keys` and `/tenants/webhook-secret`.

### 2026-02-01 — Initial production codebase
Full FastAPI + Postgres + Redis + Celery + MinIO + Docker Compose + K8s.

## Performance targets
- Sync extraction P95 < 8s — achievable with Gemini Flash (typically faster
  than Claude Sonnet for similar prompts).
- Async via Celery → webhook within 30s.
- Throughput 400k docs/month supported by HPA 2-20 + Celery autoscaling.

## Backlog
- P2: Field-level human review UI (separate React app)
- P2: GST portal cross-verification (vendor GSTIN active check) — explicitly
  deferred per 2026-02-04 user direction (no external calls).
- P2: S3 lifecycle policy for 90-day cold/glacier tiering — deferred.
