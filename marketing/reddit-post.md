# Reddit Post Drafts

## r/selfhosted

**Title:** Webcatch — Self-hosted webhook inspector with local LLM analysis (MIT, one Docker command)

**Body:**

I built a webhook capture and debugging tool that runs entirely on your own machine. No cloud. No accounts. Your data never leaves your server.

**Why I made it:**
Most webhook tools send your payload to someone else's cloud. That's fine for hobby projects, but when you're dealing with real user data, payment webhooks, or internal APIs, you don't want that stuff bouncing off a third-party server. Webcatch stores everything in local SQLite, runs in a single Docker container, and optionally analyzes webhooks with a local LLM.

**One command:**
```bash
docker run -d -p 9120:9120 -v ./data:/app/data ghcr.io/bellum19/webcatch:latest
```

**What it does:**
- Capture webhooks in real-time (WebSocket dashboard)
- Replay, bulk replay, and forward to backends
- Transform payloads with Python scripts before forwarding
- Verify HMAC signatures
- Infer JSON schemas automatically and validate incoming webhooks against them
- **Local LLM analysis** — Click "Analyze" on any captured webhook and your local model tells you what the payload is, flags security issues, and suggests validation steps

People often ask, what is a small local model even good for? Well, now you have a job you can give it.

MIT licensed. Optional $39 lifetime supporter license if you want to fund development and get priority help.

**Links:**
- GitHub: https://github.com/bellum19/webcatch
- Image: [hero screenshot]

Feedback welcome. What else would you want from a self-hosted webhook tool?

---

## r/webdev

**Title:** Show HN: Webcatch — Debug webhooks locally with AI analysis (MIT, Docker)

**Body:**

I got tired of webhook debugging tools that required cloud accounts, sent my payload data to their servers, or had aggressive rate limits. So I built Webcatch — a FastAPI + vanilla JS dashboard that captures, replays, and analyzes webhooks entirely locally.

**One command to run:**
```bash
docker run -d -p 9120:9120 -v ./data:/app/data ghcr.io/bellum19/webcatch:latest
```

**Features:**
- Real-time webhook capture with WebSocket updates
- Replay any webhook, or bulk replay a filtered set
- Forward to backends with optional Python transform scripts (strip PII, reshape payloads, etc.)
- HMAC signature verification
- Auto JSON schema inference + validation on incoming webhooks
- Export to Postman collection, cURL script, or CSV
- **Local LLM analysis** — On every captured webhook, click "Analyze" and your local model explains the payload, flags security concerns, and suggests responses. No OpenAI key needed.

People often ask, what is a small local model even good for? Well, now you have a job you can give it.

The LLM analysis is off by default and only runs when you click the button, so your GPU isn't getting hammered by every incoming webhook. You can flip it to auto-analyze with `WEBCATCH_ANALYZE_ON_CAPTURE=true` if you want.

MIT licensed. Optional $39 lifetime supporter license for people who want to fund the project.

**Links:**
- GitHub: https://github.com/bellum19/webcatch
- GIF demo: [gif link]

What's missing? What would make this actually useful in your workflow?

---

## r/SideProject

**Title:** I built a webhook inspector that runs 100% locally — with AI analysis via local LLM ($0/mo hosting)

**Body:**

Most developer tools for webhooks are cloud-hosted SaaS. I wanted something I could run on a $5 VPS without worrying about data leaving the box. So I built Webcatch.

**The pitch:**
- One Docker command, runs anywhere
- SQLite storage, no database to configure
- Real-time dashboard (WebSocket, no build step)
- Capture, replay, forward, transform, verify signatures
- **AI analysis powered by your own local LLM** — llama.cpp, Ollama, vLLM, whatever you run

People often ask, what is a small local model even good for? Well, now you have a job you can give it.

The whole thing is MIT licensed. I added an optional $39 lifetime supporter license for anyone who wants to chip in, but the full feature set is completely free and open source.

**Try it:**
```bash
docker run -d -p 9120:9120 -v ./data:/app/data ghcr.io/bellum19/webcatch:latest
```

GitHub: https://github.com/bellum19/webcatch

Curious what people think. Would you use this? What's the biggest pain point with webhooks for you?
