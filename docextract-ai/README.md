# DocExtract AI

Production-grade document intelligence SaaS API for Indian GST documents
(Tax Invoices, Delivery Challans, Packing Lists, Purchase Orders, Credit/Debit Notes, E-Way Bills).

## Stack

- **API**: FastAPI 0.111, Uvicorn (4 workers)
- **DB**: PostgreSQL 15 (SQLAlchemy 2.0, Alembic migrations)
- **Queue**: Celery 5.4 with Redis broker
- **Storage**: MinIO (S3-compatible)
- **OCR**: PaddleOCR (primary) + pytesseract (fallback), OpenCV preprocessing
- **LLM**: Google Gemini Flash `gemini-2.0-flash` (configurable via `LLM_MODEL`). Get a free key from https://aistudio.google.com
- **Auth**: JWT (python-jose) + API Key (bcrypt-hashed)
- **Rate limiting**: slowapi (per tenant)
- **Observability**: structlog, Prometheus, Sentry
- **Deploy**: Docker Compose (dev) + Kubernetes (prod) with HPA, PDB, ResourceQuota

## Quick start (Docker Compose)

```bash
cp .env.example .env
# edit GEMINI_API_KEY (get a free key at https://aistudio.google.com)
docker compose up -d --build
docker compose exec api alembic upgrade head
```

API: http://localhost:8000/docs
MinIO console: http://localhost:9001 (minioadmin / minioadmin)

## Create first tenant

```bash
docker compose exec api python -m app.scripts.bootstrap_tenant \
  --name "Acme Corp" --email admin@acme.com --password "ChangeMe!123"
```

It prints the API key — save it.

## Extract a document

```bash
curl -X POST http://localhost:8000/api/v1/extract \
  -H "X-API-Key: <api-key>" \
  -F "file=@sample_invoice.pdf"
```

## Tests

```bash
pytest -q
```

## Kubernetes

```bash
kubectl apply -f k8s/
```

HPA scales 2–20 pods on CPU > 70%.

## Architecture

```
client → nginx (TLS, rate limit) → FastAPI (api)
                                     ├── PostgreSQL (metadata, multi-tenant)
                                     ├── Redis (cache + Celery broker)
                                     ├── MinIO (raw file storage)
                                     └── Celery worker
                                            ├── OCR (Paddle / Tesseract)
                                            ├── LLM extraction (Gemini Flash)
                                            └── validation + webhook
```

## Performance targets

- Sync extraction P95: < 8s
- Async extraction: webhook within 30s
- Throughput: 400k docs / month (~185/hr sustained, 500/hr peak)
- Field-level confidence: > 95%

## License

Proprietary.
