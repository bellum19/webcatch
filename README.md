# Webcatch 🔍

> Self-hosted webhook capture, replay, and analysis. All data stays on your machine.

[![Docker](https://img.shields.io/badge/docker-ready-blue.svg)](https://www.docker.com/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)

## Why Webcatch?

Most webhook tools send your data to someone else's cloud. Webcatch doesn't. Everything runs locally — your data, your server, your rules.

- **🔒 Privacy-first** — SQLite storage. No telemetry. No cloud lock-in.
- **📡 Real-time dashboard** — WebSocket-powered live updates.
- **🔄 Replay & proxy** — Resend webhooks, forward to backends, transform payloads with Python scripts, verify HMAC signatures.
- **🧠 AI analysis** — Analyze webhooks with your local LLM (optional).
- **🔍 Search & diff** — Full-text search. Side-by-side webhook comparison.

---

## Quick Start

### Docker (recommended)

```bash
git clone https://github.com/bellum19/webcatch.git
cd webcatch
docker compose up -d
```

Open http://localhost:9120

### Local Python

```bash
cd webcatch
pip install -r requirements.txt
python main.py
```

---

## Features

| Feature | Free | Pro |
|---------|------|-----|
| Unlimited endpoints | ✅ | ✅ |
| Real-time dashboard | ✅ | ✅ |
| Webhook replay | ✅ | ✅ |
| Forwarding / proxy | ✅ | ✅ |
| Signature verification | ✅ | ✅ |
| Search & filter | ✅ | ✅ |
| Webhook diff | ✅ | ✅ |
| AI analysis | ✅ | ✅ |
| **Postman / cURL export** | ✅ | ✅ |
| **Transform scripts** | ✅ | ✅ |
| Unlimited history | 100 recent | Unlimited |
| Team sharing | ❌ | Up to 5 users |
| Custom responses | ❌ | ✅ |
| Bulk replay | ❌ | ✅ |
| Priority support | ❌ | ✅ |

---

## Configuration

Create a `.env` file:

```bash
# App
INSPECTOR_PORT=9120
INSPECTOR_HOST=0.0.0.0

# Stripe (optional, for Pro license sales)
STRIPE_SECRET_KEY=sk_...
STRIPE_PUBLISHABLE_KEY=pk_...
STRIPE_WEBHOOK_SECRET=whsec_...
SUCCESS_URL=https://yourdomain.com/success?session_id={CHECKOUT_SESSION_ID}
CANCEL_URL=https://yourdomain.com/

# Local LLM (optional, for AI analysis)
LOCAL_LLM_URL=http://127.0.0.1:8081/v1/chat/completions
LOCAL_LLM_MODEL=qwen-local
```

---

## Architecture

- **FastAPI** backend + SQLite storage
- **Vanilla JS** dashboard (no build step)
- **WebSocket** real-time updates
- **Docker** single-container deploy
- Optional **local LLM** via OpenAI-compatible API (llama.cpp, Ollama, etc.)

---

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/endpoints` | POST | Create endpoint |
| `/api/endpoints` | GET | List endpoints |
| `/api/webhooks` | GET | List captured webhooks |
| `/api/webhooks/export?format=postman` | GET | Export as Postman collection |
| `/api/webhooks/export?format=curl` | GET | Export as cURL script |
| `/api/webhooks/export?format=csv` | GET | Export as CSV |
| `/api/endpoints/{id}/config` | GET/PUT | Get/set endpoint config (forward URL, transforms, filters, custom responses) |
| `/wh/{id}` | ANY | Capture webhooks |
| `/api/webhooks/{id}/replay` | POST | Replay webhook |
| `/api/webhooks/{id}/export` | GET | Export single webhook |
| `/api/webhooks/{a}/diff/{b}` | GET | Compare webhooks |
| `/ws` | WebSocket | Live updates |

Full API docs at `/docs` when running.

---

## Transform Scripts

Before forwarding a webhook, you can mutate it with a Python script. Available variables:

- `method` — HTTP method (str)
- `url` — Target URL (str)
- `headers` — Dict of headers
- `body` — Request body (str or None)
- `query` — Dict of query params

Example — strip PII before forwarding:

```python
import json
data = json.loads(body)
data.pop("email", None)
data.pop("ssn", None)
body = json.dumps(data)
```

Scripts run in a restricted sandbox with a 5-second timeout. If a script fails, the original webhook is forwarded unchanged and the error is logged.

---

## License

MIT — see [LICENSE](LICENSE)

---

Built for developers who care about privacy.
