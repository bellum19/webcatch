# Webcatch vs. Competitors

## Why Webcatch?

Every other webhook tool sends your data to their cloud. Webcatch doesn't. It's a single Docker container that runs on your machine, captures webhooks, analyzes them with a local LLM, and never phones home.

---

## Feature Matrix

| Feature | Webcatch | Hookdeck | Svix | Webhook.site | ngrok |
|---------|----------|----------|------|--------------|-------|
| **Self-hosted** | ✅ Open source | ❌ Cloud only | ❌ Cloud only | ❌ Cloud only | ❌ Cloud only |
| **Data stays local** | ✅ SQLite on disk | ❌ On their servers | ❌ On their servers | ❌ On their servers | ❌ Proxied through their infra |
| **No sign-up** | ✅ Just run Docker | ❌ Required | ❌ Required | ❌ Required | ❌ Required |
| **Webhook replay** | ✅ One click | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Payload transformation** | ✅ Python scripts | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **AI analysis** | ✅ Local LLM (Ollama, llama.cpp) | ❌ No | ❌ No | ❌ No | ❌ No |
| **Schema inference** | ✅ Auto-infers from history | ❌ No | ❌ No | ❌ No | ❌ No |
| **Schema validation** | ✅ Real-time anomaly detection | ❌ No | ❌ No | ❌ No | ❌ No |
| **OpenAPI export** | ✅ From inferred schema | ❌ No | ❌ No | ❌ No | ❌ No |
| **Signature verification** | ✅ Stripe, GitHub, Shopify | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Postman export** | ✅ Full collections | ❌ No | ❌ No | ❌ No | ❌ No |
| **cURL export** | ✅ Bulk or single | ❌ No | ❌ No | ❌ No | ❌ No |
| **CSV export** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |
| **Custom responses** | ✅ Status, headers, body | ✅ Yes | ✅ Yes | ✅ Limited | ❌ No |
| **Filter rules** | ✅ Method, header, body | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Retention limits** | ✅ Configurable | ❌ No | ❌ No | ❌ No | ❌ No |
| **Bulk replay** | ✅ Pro | ❌ No | ❌ No | ❌ No | ❌ No |
| **Real-time dashboard** | ✅ WebSocket | ✅ Yes | ✅ Yes | ❌ Polling | ❌ CLI only |
| **Webhook diff** | ✅ Side-by-side | ❌ No | ❌ No | ❌ No | ❌ No |
| **Search** | ✅ Full-text | ✅ Yes | ✅ Yes | ❌ No | ❌ No |
| **Team sharing** | ✅ Up to 5 (Pro) | ✅ Paid plans | ✅ Enterprise | ❌ No | ❌ No |
| **Pricing** | **Free / $39 lifetime** | $25+/mo | $100+/mo | Free / Pro | Free / Pro |
| **Telemetry** | ✅ None | ❌ Yes | ❌ Yes | ❌ Yes | ❌ Yes |
| **Offline capable** | ✅ Yes | ❌ No | ❌ No | ❌ No | ❌ No |

---

## When to use what

**Use Webcatch when:**
- You care about privacy (healthcare, fintech, legal)
- You want to self-host for compliance (GDPR, HIPAA, SOC2)
- You have a local LLM and want AI analysis without API keys
- You want schema inference and OpenAPI export
- You hate monthly subscriptions
- You want everything in one container

**Use Hookdeck / Svix when:**
- You need managed reliability (SLAs, retries, queuing)
- You have a large team that needs RBAC and audit logs
- You don't want to run any infrastructure
- You need webhook verification as a service

**Use Webhook.site when:**
- You just need a quick throwaway URL for 5 minutes
- You don't care about replay, analysis, or history

**Use ngrok when:**
- You need to tunnel local dev servers to the internet
- Webhook inspection is a secondary concern
