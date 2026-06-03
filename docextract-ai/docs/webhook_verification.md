# Webhook Signature Verification

DocExtract AI signs every outbound webhook payload with **HMAC-SHA256** so you can
verify it came from us and detect replays.

## Headers we send

| Header                        | Example                                         |
| ----------------------------- | ----------------------------------------------- |
| `X-DocExtract-Signature`      | `t=1738502400,v1=8f4a...e1c`                    |
| `X-DocExtract-Timestamp`      | `1738502400`                                    |
| `Content-Type`                | `application/json`                              |
| `User-Agent`                  | `DocExtract-AI/1.0`                             |

The signature is `HMAC-SHA256(secret, f"{timestamp}.{raw_body}")` — exactly the
**Stripe** scheme. Including the timestamp inside the signed payload prevents
replay attacks even if your endpoint is HTTPS but somehow the signature leaks.

## Getting your secret

```bash
curl -X POST https://api.docextract.ai/api/v1/tenants/webhook-secret/rotate \
  -H "Authorization: Bearer $JWT"
# {
#   "secret": "whsec_AbCd...xyz",     # shown only once
#   "created_at": "2026-02-02T10:11:12Z"
# }
```

Store it in your application's secret manager. To disable signing:

```bash
curl -X DELETE https://api.docextract.ai/api/v1/tenants/webhook-secret \
  -H "Authorization: Bearer $JWT"
```

## Verifying a webhook — Python (FastAPI)

```python
import hmac, hashlib, time
from fastapi import FastAPI, Header, HTTPException, Request

WEBHOOK_SECRET = "whsec_AbCd...xyz"
TOLERANCE = 300  # seconds

def verify(body: bytes, header: str, secret: str, tolerance: int = TOLERANCE) -> bool:
    parts = dict(p.split("=", 1) for p in header.split(",") if "=" in p)
    ts, received = parts.get("t"), parts.get("v1")
    if not ts or not received:
        return False
    if abs(time.time() - int(ts)) > tolerance:
        return False  # replay window expired
    signed = f"{ts}.".encode() + body
    expected = hmac.new(secret.encode(), signed, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, received)

app = FastAPI()

@app.post("/webhooks/docextract")
async def receive(req: Request, x_docextract_signature: str = Header(...)):
    body = await req.body()
    if not verify(body, x_docextract_signature, WEBHOOK_SECRET):
        raise HTTPException(401, "invalid_signature")
    event = await req.json()
    # ... persist / process event ...
    return {"received": True}
```

## Verifying a webhook — Node.js (Express)

```js
const express = require("express");
const crypto = require("crypto");

const WEBHOOK_SECRET = process.env.DOCEXTRACT_WEBHOOK_SECRET;
const TOLERANCE = 300; // seconds

function verify(rawBody, header, secret) {
  const parts = Object.fromEntries(
    header.split(",").map((p) => p.trim().split("="))
  );
  const ts = parseInt(parts.t, 10);
  const received = parts.v1;
  if (!ts || !received) return false;
  if (Math.abs(Date.now() / 1000 - ts) > TOLERANCE) return false;
  const signed = `${ts}.` + rawBody.toString("utf8");
  const expected = crypto
    .createHmac("sha256", secret)
    .update(signed)
    .digest("hex");
  // constant-time compare
  const a = Buffer.from(expected, "utf8");
  const b = Buffer.from(received, "utf8");
  return a.length === b.length && crypto.timingSafeEqual(a, b);
}

const app = express();

// IMPORTANT: capture raw body — JSON parsing destroys the bytes we signed.
app.post(
  "/webhooks/docextract",
  express.raw({ type: "application/json" }),
  (req, res) => {
    const sig = req.header("X-DocExtract-Signature");
    if (!verify(req.body, sig, WEBHOOK_SECRET)) {
      return res.status(401).send("invalid_signature");
    }
    const event = JSON.parse(req.body.toString("utf8"));
    // ... persist / process event ...
    res.json({ received: true });
  }
);

app.listen(3000);
```

## Verifying with our own helper (Python — if you're using docextract-ai as a library)

```python
from app.services.webhook import verify_signature

ok = verify_signature(
    body=raw_request_body,
    header_value=request.headers["X-DocExtract-Signature"],
    secret="whsec_AbCd...xyz",
)
```

## Key rotation guidance

1. Call `POST /tenants/webhook-secret/rotate` to generate a new secret. The old
   secret immediately stops working for outbound webhooks.
2. To avoid a window of failed deliveries, update your receiver to accept
   **either** the old or new secret for a brief overlap window before rotating.
   (Operationally: keep `WEBHOOK_SECRET_OLD` + `WEBHOOK_SECRET_NEW` env vars,
   verify against both, then drop `OLD` after a few hours.)
3. If you suspect compromise, rotate immediately and invalidate the old
   secret by simply rotating again or `DELETE /tenants/webhook-secret`.

## Replay protection

- We reject any signature whose timestamp differs from server time by more than
  300 seconds. Adjust `TOLERANCE` on your side to match.
- We do not retain delivered event IDs server-side. If your handler is not
  idempotent, dedupe on `document_id` (which is unique per extraction).
