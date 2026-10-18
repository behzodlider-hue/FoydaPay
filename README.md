# FoydaPay

**Debt-rescue agent for borrowers.** It finds the money for next month's loan payment — **cut** spending, **earn** with vetted side jobs, **negotiate** a restructuring — and cannot be talked into sending money to a scammer.

Built by team **Capital Guardians** (Tashkent, Uzbekistan) for the 2026 Shenzhen International FinTech Competition, International AI Track, Topic A: Personal Finance Assistant.

**Live demo:** https://foydapay.onrender.com

## What's here

| Path | What it is |
|---|---|
| [`backend/`](backend/) | The agent: FastAPI, LLM tool use (Gemini free tier or Claude), policy guard, 19 tools, sandbox account, hash-chained audit log, web chat, 60 tests. Start with [`backend/README.md`](backend/README.md). |
| [`docs/technical_documentation.md`](docs/technical_documentation.md) | Architecture, algorithms, providers, testing, deployment |
| [`docs/security_self_assessment.md`](docs/security_self_assessment.md) | Permission tiers, attack tests and results, known risks |
| [`evidence/live-run-20261018T161742Z/`](evidence/live-run-20261018T161742Z/) | Execution evidence: 20/20 live-model scenarios — transcripts, summary, per-scenario audit logs |
| `foydapay-agent-demo.html` | Early browser-only prototype (rules engine) |
| `business-model-canvas.html` | Business model |

## Quick start

```bash
cd backend
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q
uvicorn app.main:app              # http://localhost:8000
```

Set `GEMINI_API_KEY` (free at aistudio.google.com) for LLM mode. Without a key the app runs on its rules engine.

All data is synthetic. Not financial or legal advice.
