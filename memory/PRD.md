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
- P1: Webhook signature verification example in docs
- P1: Per-tenant API-key rotation endpoint
- P2: Async webhook retry visibility (Celery flower)
- P2: Per-document-type prompts (DELIVERY_CHALLAN, EWAY_BILL specialised hints)
- P2: GST portal cross-verification (vendor GSTIN active check)
- P2: Field-level human review UI (separate React app)
- P2: S3 lifecycle policy for cold/glacier tiering after 90 days
