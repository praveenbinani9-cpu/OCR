# DocExtract AI — PRD

## Original problem statement
Production-grade document intelligence SaaS API for Indian GST documents.
Stack: Python 3.11, FastAPI 0.111, SQLAlchemy 2.0, PostgreSQL, Redis, Celery 5.4,
MinIO (S3), Anthropic Claude `claude-sonnet-4-20250514`, PaddleOCR + pytesseract,
Docker Compose, Kubernetes (HPA / PDB / ResourceQuota).

## User choices (verbatim)
- Stack: option (a) — generate full production code as specified (Postgres, Redis,
  Celery, MinIO, Docker, K8s). Not runnable in current sandbox.
- LLM key: **Emergent Universal LLM Key** for Claude Sonnet 4
  (`claude-4-sonnet-20250514` via `emergentintegrations`).
- OCR: **pytesseract primary** in runtime; **PaddleOCR via feature flag**
  (`OCR_ENGINE=paddle`) with automatic fallback on failure.
- Frontend: **None** — backend + Postman collection only.

## Architecture (delivered)
```
client → nginx (TLS, per-IP rate-limit) → FastAPI api (uvicorn x4)
                                            ├── PostgreSQL (multi-tenant)
                                            ├── Redis (cache + Celery broker)
                                            ├── MinIO (raw file storage, SSE-AES256)
                                            └── Celery worker (4 concurrency, queues:
                                                  document_processing / notifications)
                                                  ├── OCR (Paddle/Tesseract + OpenCV)
                                                  ├── LLM (Claude Sonnet 4)
                                                  └── webhook (HMAC-SHA256 signature)
```

## What's implemented (2026-02-01)
- 83 files under `/app/docextract-ai/`
- Models: tenants, users (with role enum), documents, extractions, review_queue,
  audit_logs, api_keys — with cross-dialect `GUID` and `JSONType` (PG-native JSONB
  / SQLite-friendly fallback).
- API endpoints (all under `/api/v1`):
  - `POST  /auth/token` (JWT, 10/min)
  - `POST  /auth/api-key` (admin-only)
  - `POST  /extract` (multipart, sync + async via Celery, webhook_url)
  - `GET   /documents` (paginated, tenant-scoped)
  - `GET   /documents/{id}` (returns ExtractionResponse)
  - `GET   /review-queue` (pending items)
  - `PATCH /review-queue/{id}` (reviewer/admin only)
  - `GET   /tenants/usage`
  - `GET   /health` (DB + Redis + S3 + OCR checks)
  - `GET   /metrics` (Prometheus exposition)
- Auth: JWT (python-jose) + API Key (bcrypt-hashed). Tenant resolution via
  `Depends(get_principal)`, surfaced to middleware for rate-limit + audit.
- Validation engine: GSTIN regex, multi-format date parsing, amount + tax
  reconciliation (±1 tolerance), duplicate detection on (tenant, document_number,
  vendor_gstin, document_date).
- LLM service: Emergent (anthropic) primary, direct Anthropic SDK fallback. Tenacity
  retries (3, exponential), JSON envelope stripping (markdown fence + greedy slice),
  self-correction pass on amount mismatch.
- OCR service: OpenCV preprocessing (deskew via Hough, CLAHE, denoise, adaptive
  threshold), pytesseract default, lazy-imported PaddleOCR with automatic
  fall-through.
- Storage: boto3 S3 client, SSE-AES256, presigned-URL helper, bucket bootstrap.
- Celery: `app.workers.tasks.process_document`, `send_webhook`, `cleanup_old_files`
  (beat 03:00 UTC daily). 4 concurrency, prefetch_multiplier=1, ack_late.
- Observability: structlog JSON logging, Prometheus histograms (request latency,
  extraction latency, confidence histogram), Sentry (`SENTRY_DSN`), audit
  middleware writing on every mutating request.
- Rate limiting: slowapi with Redis storage in prod, memory storage in tests.
- Multi-tenant isolation: every query filters by `tenant_id`, verified by
  integration test (`tests/integration/test_multi_tenant_isolation.py`).
- Tests: **24 pass** (unit: validation, OCR, extraction, auth; integration:
  /extract endpoint with mocked S3/OCR/LLM, cross-tenant isolation).
- Docker: API + worker Dockerfiles, docker-compose with postgres / redis / minio
  / nginx, healthchecks, TLS-ready nginx with per-route rate limits.
- Kubernetes: namespace, ConfigMap, Secret template, Deployment (api + worker),
  Service, HPA (min 2 / max 20 on CPU 70%, mem 80%), PDB (minAvailable 2/1),
  ResourceQuota (40 CPU / 80Gi mem) + LimitRange.
- Docs: full OpenAPI 3.0.3 spec, Postman v2.1 collection with all endpoints +
  example bodies and variables.
- Bootstrap CLI: `python -m app.scripts.bootstrap_tenant --name --email --password`
  prints the initial API key (shown once).

## Performance targets (per spec)
- Sync extraction P95 < 8s — achievable: OCR ~1-3s + Claude Sonnet ~2-4s.
- Async via Celery: webhook within 30s.
- Throughput 400k docs/month — supported by HPA 2-20 + Celery autoscaling.
- Field-level confidence > 95% — driven by Claude's structured output + correction pass.

## Verification
- `pytest -q` → **24 passed**
- `ruff` lint → clean
- `python -c "from app.main import app"` → imports clean, 14 routes registered
- Note: full runtime (Postgres / Redis / MinIO / Claude calls) requires
  `docker compose up` — not exercisable inside the current sandbox per user choice (1a).

## Backlog (P0/P1/P2)
- ~~P1: Webhook signature verification example in docs~~ ✅ done 2026-02-02
- ~~P1: Per-tenant API-key rotation endpoint~~ ✅ done 2026-02-02
- ~~P2: Async webhook retry visibility (webhook_deliveries log + endpoint)~~ ✅ done 2026-02-03
- ~~P2: Per-document-type prompts (DELIVERY_CHALLAN, EWAY_BILL)~~ ✅ done 2026-02-03
- P2: GST portal cross-verification (vendor GSTIN active check) — deferred
- P2: Field-level human review UI (separate React app)
- P2: S3 lifecycle policy for cold/glacier tiering — deferred

## 2026-02-04 update — validation engine simplified (BREAKING)

Per explicit user direction: stripped the validation surface down to exactly
three checks. No external API calls anywhere (was already the case; now also
documented as a hard invariant). No date parsing, no GSTIN structural regex,
no tax-component reconciliation.

**Kept** (only these three, plus errors list):
1. `gstin_valid` — true iff every GSTIN present is exactly 15 characters
   (whitespace stripped). No structure, no checksum, no portal lookup.
2. `duplicate_detected` — DB check on
   `(tenant_id, document_number, vendor_gstin, document_date)` already exists.
3. `amounts_reconciled` — `subtotal + (cgst+sgst+igst, or total_tax if components
   absent) ≈ grand_total` within ±1 rupee.

**Removed** (BREAKING — `ValidationResult` shape changed):
- `date_valid` (date parsing entirely dropped from `app/services/validation.py`)
- `tax_reconciled` (no longer separately reported — folded into amounts check)
- `parse_date()` helper removed
- `GSTIN_REGEX` removed in favour of `len == 15`

**Callers updated** in lockstep:
- `app/api/v1/routes/extract.py` — correction-pass trigger now keys only on
  `not validation.amounts_reconciled`.
- `app/api/v1/routes/documents.py` — `review_required` aggregation dropped
  `tax_reconciled` and `date_valid` checks.
- `is_review_required()` — same.
- `docs/openapi.yaml` — `ValidationResult` schema reduced to 4 fields.

**Tests rewritten**: 11 tests in `test_validation_engine.py` covering only the
three kept behaviours, including a guard test asserting the public surface is
exactly `{gstin_valid, amounts_reconciled, duplicate_detected, errors}` so any
future drift fails fast. **Total now 63 passing tests.**


- New model `WebhookDelivery` + migration `0003_webhook_deliveries`
  (id, document_id, tenant_id, url, response_status, response_body, attempt_count,
  delivered_at, created_at) with indexes on `document_id` and
  `(tenant_id, created_at)`.
- New endpoint: `GET /api/v1/webhook-deliveries?document_id={id}` —
  tenant-scoped, paginated (default page_size=50, max 500), newest first,
  requires `document_id` query param. Returns one row per HTTP attempt with
  response excerpt (≤4 KB), attempt number, and `delivered_at` (set only on
  2xx).
- `services/webhook.py` refactored: new `deliver()` returns a `DeliveryResult`
  dataclass (never raises) so the worker can log every attempt deterministically.
  Removed in-process tenacity retry — Celery now owns the retry loop (cleaner
  attempt accounting, no double-counting). Legacy `post_webhook()` retained as a
  thin wrapper for backward compatibility.
- `workers/tasks.send_webhook` now persists a `webhook_deliveries` row on each
  invocation (success or failure), with `attempt_count` = (# of prior rows for
  the same (document_id, url)) + 1. `delivered_at` set on 2xx. After
  `max_retries` exhausted, returns `{status: "failed", http_status: …}`
  instead of raising — the failed delivery is still in the log table.
- `prompts/extraction.py`: added three specialization blocks (EWAY_BILL,
  DELIVERY_CHALLAN, TAX_INVOICE) and `detect_document_type(ocr_text)` keyword
  classifier that emits `EWAY_BILL | DELIVERY_CHALLAN | TAX_INVOICE | UNKNOWN`.
  Ties resolve to `UNKNOWN` (let the LLM decide).
- `services/extraction.py` now pre-classifies the OCR text and passes the hint
  into `build_user_prompt(...,  document_type_hint=...)` so Claude receives
  document-specific guidance (e.g. EWBs map Generator→vendor, Recipient→customer;
  Delivery Challans expect zero tax).
- OpenAPI 3.0.3 + Postman collection updated with the new route.
- Tests: 9 prompt-specialization unit tests, 7 webhook-delivery tests
  (tenant isolation on `document_id`, pagination + ordering, 422 missing
  param, 401 unauthenticated, success row written, failure row written with
  attempt_count incremented). **Total now 59 passing tests.**

## 2026-02-02 update — P1 items shipped
- Added Stripe-style HMAC-SHA256 webhook signing: `X-DocExtract-Signature: t=<unix>,v1=<hex>` plus `X-DocExtract-Timestamp`, signed payload = `f"{ts}.{body}"`, replay window 300s, constant-time compare.
- New endpoints (JWT-only, tenant-scoped):
  - `GET /api/v1/auth/api-keys` (optionally `?include_revoked=true`)
  - `POST /api/v1/auth/api-keys/{id}/rotate` → returns new plaintext once, old stops working immediately
  - `DELETE /api/v1/auth/api-keys/{id}` → soft revoke (idempotent), revoked keys skipped at auth time
  - `GET /api/v1/tenants/webhook-secret` → `{configured: bool}` (never returns the secret)
  - `POST /api/v1/tenants/webhook-secret/rotate` → returns new `whsec_…` plaintext once
  - `DELETE /api/v1/tenants/webhook-secret` → disables signing
- Schema migration: `0002_webhook_and_key_revoke.py` adds `tenants.webhook_secret` + `api_keys.revoked_at`.
- Worker now looks up tenant `webhook_secret` and passes it to `send_webhook`.
- Docs: `docs/webhook_verification.md` with Python (FastAPI) + Node (Express) verification examples.
- Tests added: 7 webhook-signature unit tests, 8 API-key lifecycle integration tests (rotate, revoke, cross-tenant isolation, idempotency, API-key auth rejected for key management), 4 webhook-secret integration tests. **Total now 43 passing tests.**
