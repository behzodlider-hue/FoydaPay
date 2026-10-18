# FoydaPay backend

Debt-rescue agent for the Shenzhen FinTechathon 2026, International AI Track, Topic A: Personal Finance Assistant.
It helps a borrower find money for loan payments three ways — **cut** spending, **earn** with checked side jobs,
**negotiate** with the bank — and blocks scammers and predatory loans along the way.

- **LLM agent:** Claude (`claude-opus-5-5`) with tool use, in a manual agentic loop.
- **Policy guard in code:** every tool call passes through it, whether it comes from the model or from the fallback engine.
- **Rules-engine fallback:** answers when no LLM is configured or an API call fails. It uses the same tools, guard and audit log.
- **Sandbox account:** synthetic user Jasur — income 6 000 000 UZS, 3 loans, debt load 52.5%. No real people or brands.

## Run locally

```bash
python -m venv .venv
.venv\Scripts\activate            # Linux/macOS: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m pytest -q               # 56 tests, no API calls
uvicorn app.main:app --reload     # http://localhost:8000
```

Without credentials the app runs in **rules mode** (badge "Rules engine"). To use Claude, set a key in the environment, never in code:

```powershell
# Windows PowerShell (prompts for the key without echoing it or saving it in history):
$env:ANTHROPIC_API_KEY = [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR((Read-Host -AsSecureString "Anthropic API key")))
Test-Path env:ANTHROPIC_API_KEY   # True = the app will see it
```

On Linux/macOS: `export ANTHROPIC_API_KEY=<API_KEY>`. In PowerShell, `set NAME=value` does not create an environment variable, and the app does not read `.env` files.

**Free option: Google Gemini.** Get a free key at aistudio.google.com → Get API key (no card needed), then set `GEMINI_API_KEY` the same way. With only a Gemini key set, the app uses Gemini automatically, through its OpenAI-compatible endpoint.

| Variable | Default | Meaning |
|---|---|---|
| `GEMINI_API_KEY` | — | Turns on LLM mode with Gemini (free tier, rate-limited). On Render, a secret. |
| `ANTHROPIC_API_KEY` | — | Turns on LLM mode with Claude (paid). Takes priority if both keys are set, unless `FOYDAPAY_PROVIDER=gemini`. |
| `FOYDAPAY_PROVIDER` | `auto` | `auto`, `anthropic` or `gemini` |
| `FOYDAPAY_GEMINI_MODEL` | `gemini-3.5-flash-lite` | If the free tier rejects it, check the free models and limits at aistudio.google.com/rate-limit and set another Flash model. |
| `FOYDAPAY_GEMINI_EFFORT` | `low` | Gemini thinking level via `reasoning_effort` |
| `FOYDAPAY_LLM` | `auto` | `0` = force rules mode; `1` = allow Claude via an `ant auth login` profile |
| `FOYDAPAY_MODEL` | `claude-opus-5-5` | Claude model. Changing it changes cost and quality; that is the team's call. |
| `FOYDAPAY_EFFORT` | `medium` | `low` / `medium` / `high` / `xhigh` / `max` |
| `FOYDAPAY_FALLBACKS` | `1` | Server-side refusal fallback (`fallbacks: "default"`). Claude API only; set `0` on other platforms. |

**Cost:** the Claude API is paid; there is no free tier. Every jury test and demo message costs money. Protections in place:
- a rate limit of 20 messages per minute per IP;
- input capped at 1000 characters;
- at most 8 tool steps per message;
- prompt caching of the system prompt and tools.

Before the demo, check usage in the Anthropic Console and set a spending limit there.

## Architecture

```
Browser chat (app/static/index.html)
   │  POST /api/chat · POST /api/confirm · GET /api/state · GET /api/audit.jsonl
   ▼
FastAPI (app/main.py) ── session store (in memory, 2 h TTL)
   │
   ▼
Agent (app/agent.py) ── Claude tool use, manual loop ──┐   fallback: rules engine (app/rules.py)
   │                                                    │
   ▼                                                    ▼
toolbox.call(name, args)  (app/toolbox.py)
   validate input → policy guard (T0–T3, trusted payees, daily limit) → run / prepare confirmation / block
   │
   ▼
Sandbox account (app/sandbox.py) + SHA-256 hash-chained audit log (app/audit.py)
```

### Permission tiers (enforced in `toolbox.py`, not in the prompt)

| Tier | Tools | Behaviour |
|---|---|---|
| T0 read | `get_account_overview`, `recent_actions`, `spending_breakdown`, `compare_months`, `analyze_bills`, `find_side_jobs`, `analyze_message` | Run immediately |
| T1 draft | `build_budget`, `build_rescue_plan`, `draft_restructuring_request` | Run immediately; nothing leaves the session |
| T2 execute | `cancel_subscriptions`, `pay_bill`, `pay_loan`, `book_side_jobs`, `set_earnings_rule`, `send_restructuring_request` | Prepared and checked (funds, trusted payee, daily limit, scam vetting). Waits for a one-time confirmation bound to that exact action. Re-checked at execution. Any new message expires it. The model cannot confirm. |
| T3 forbidden | `transfer_to_card`, `take_new_loan`, `change_limit` | Always blocked and logged |

Other safeguards:
- **No access to other customers:** no tool takes a customer id.
- **Untrusted text stays data:** transaction notes and pasted messages are returned as data, marked untrusted. The model is told never to follow instructions in them, and the guard blocks the dangerous actions regardless.
- **Card numbers are masked** in the audit log.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/healthz` | Mode (`llm` / `rules`) and model |
| POST | `/api/session` | New sandbox session → `session_id` |
| POST | `/api/chat` | `{session_id, message}` → `{reply, events, mode, state}`; `events` may contain a `confirm` card |
| POST | `/api/confirm` | `{session_id, confirmation_id, approve}` → executes or cancels the pending action |
| GET | `/api/state` | Account, subscriptions, bookings, audit tail, chain check |
| GET | `/api/audit.jsonl` | Full hash-chained log: the "execution evidence" for the submission |

## Tests (56, offline)

| File | What it covers |
|---|---|
| `tests/test_toolbox.py` | The 12 tasks and 8 attacks from the browser demo at the tool and guard level, plus untrusted payee, daily limit, stale confirmation, invalid input, audit tampering, strict schemas |
| `tests/test_agent_loop.py` | Agent loop with a scripted fake Claude: T2 returns a card (not an execution), T3 blocked, parallel tool results in one message, refusal, API failure → rules fallback with valid history, typed "yes", pending expiry |
| `tests/test_sdk_wire.py` | The real Anthropic SDK over a mock transport: headers, `fallbacks`, `output_config`, caching, strict tools, `tool_result` round trip |
| `tests/test_rules_and_api.py` | EN/RU/UZ routing and attacks, corrections, plus the HTTP flow end to end (confirm once, block a transfer, audit export with masked card) |

**Not covered offline:** how well Claude itself picks tools and words answers. That needs a short paid eval: run the 20 demo scenarios against the live model once the key is set, and save the transcripts plus `audit.jsonl` as evidence.

## Deploy (Render / Docker)

```bash
docker build -t foydapay .
docker run -p 8000:8000 -e ANTHROPIC_API_KEY=<API_KEY> foydapay
```

On Render:
1. Create a new Web Service from the repo; Docker runtime.
2. Add `ANTHROPIC_API_KEY` as a secret environment variable.
3. Use `/healthz` as the health check.

## Known limitations

- **Sessions live in memory:** a restart clears them, and they don't work across several instances.
- **The rate limit is per process,** not global.
- **The risk numbers are rules plus simple finance math.** The trained default model from QarzQutqaruv is not connected.
- **The sandbox is synthetic:** no real bank or payment APIs.
