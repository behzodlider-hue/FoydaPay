# FoydaPay — Technical Documentation

**Team:** Capital Guardians (Uzbekistan) · **Track:** International AI Track, Topic A — Personal Finance Assistant
**Live demo:** `<RENDER URL>` · **Source code:** `<GITHUB URL>`

## 1. Problem and user

Household debt in Uzbekistan is a real pain point:
- In a 2026 Central Bank survey of 5,800 people, **61% of borrowers** said they struggle to repay on time.
- The average debt burden is **51% of income**.
- **8%** of borrowers took a new loan to repay an old one.

At the same time, card fraud grew sharply. Between 2021 and 2024 more than **$148.9M** was stolen from citizens, and 98% of cases involved bank cards. People under debt stress are the easiest targets: fake "collectors", jobs that require prepayment, instant microloans.

**User:** a salaried or self-employed borrower with two or more loans whose payments exceed 50% of income.
**Job of the agent:** find the money for next month's loan payments without harming the user, using three levers:

1. **Cut:** budget, bill analysis and spending insights (the Topic A core).
2. **Earn:** checked side jobs that fit the user's free time and skills. Scam-like offers are rejected.
3. **Negotiate:** a restructuring request to the bank, with the extra interest shown honestly.

Through all three, the agent refuses to move money to unknown cards, take loans, or change limits.

## 2. Architecture

```
Web chat (static HTML)  ──HTTP──▶  FastAPI (app/main.py)
                                    │ sessions (in memory, 2 h TTL), rate limit, input limits
                                    ▼
                         Agent (app/agent.py)
                         LLM tool-use loop, ≤ 8 steps/turn
                         providers: Gemini (OpenAI-compatible) │ Claude (Anthropic SDK)
                         fallback: rules engine (app/rules.py) on missing key / API error / quota
                                    │  every tool call
                                    ▼
                         toolbox.call()  (app/toolbox.py)
                         1. JSON-schema validation
                         2. policy guard: tiers T0–T3, trusted payees, daily limit
                         3. run │ prepare one-time confirmation │ block
                                    │
                    ┌───────────────┴───────────────┐
                    ▼                               ▼
     Sandbox account (app/sandbox.py)   Audit log (app/audit.py)
     synthetic user, 3 loans,           append-only, SHA-256 hash chain,
     bills, subscriptions, jobs         card numbers masked, JSONL export
```

**Key design decision: safety lives in code, not in the prompt.**
- The LLM proposes tool calls. The guard decides.
- A T2 tool (one that moves money or changes something) never executes inside the model loop. It returns a confirmation card, and only the user's button press, outside the model, executes it.
- The rules engine reuses exactly the same tools and guard. The app keeps working, safely, when the LLM is unavailable.

## 3. Agent loop

1. A user message arrives.
   - If an action is pending and the message is "yes" or "no", it is resolved directly, without the LLM.
   - Any other message expires the pending action.
2. The LLM receives the system prompt, the conversation and 19 tool definitions, each tagged with its tier.
3. For every tool call:
   - the arguments are validated;
   - the guard decides;
   - the result goes back as a tool result.
   Blocked calls return `blocked_by_policy` with a reason. T2 calls return `awaiting_user_confirmation`.
4. The loop ends when the model answers without tool calls, or after 8 steps.
5. The reply goes back with UI events (confirmation cards) and the account state.

**History is append-only.** Assistant messages are echoed back unchanged, including provider metadata such as Gemini thought signatures and Claude content blocks. If an API call fails mid-turn, the unfinished turn is dropped and the rules engine answers, so the history stays well-formed.

## 4. Tools (19)

| Tier | Tools | Behaviour |
|---|---|---|
| T0 read | `get_account_overview`, `recent_actions`, `spending_breakdown`, `compare_months`, `analyze_bills`, `find_side_jobs`, `analyze_message` | Run immediately |
| T1 draft | `build_budget`, `build_rescue_plan`, `draft_restructuring_request` | Run immediately; nothing leaves the session |
| T2 execute | `cancel_subscriptions`, `pay_bill`, `pay_loan`, `book_side_jobs`, `set_earnings_rule`, `send_restructuring_request` | Prepared and checked, then wait for a one-time user confirmation |
| T3 forbidden | `transfer_to_card`, `take_new_loan`, `change_limit` | Always blocked and logged. They exist so that attempts are recorded. |

## 5. Core algorithms

- **Debt load:** monthly annuity payment `P = B·r / (1 − (1+r)^−n)` per loan, with `r` the monthly rate. The total is compared with a 50%-of-income safe level.
- **Budget:**
  - fixed lines: rent, loans, utilities at their 3-month average, subscriptions actually in use;
  - target lines: groceries, transport, food-delivery cap, cafés cap;
  - the gap is income minus the total.
- **Bill analysis:**
  - a spike is a bill more than 30% above its 3-month average;
  - an unused subscription has no use for more than 30 days;
  - overlapping services in the same category are flagged.
- **Spending insights:** category totals and shares. Month-over-month change by category, with drivers such as the number of delivery orders, new subscriptions and the electricity change.
- **Rescue plan:**
  - shortfall = October-like living costs + loan payments − income;
  - cuts: unused subscriptions plus caps;
  - the remaining gap goes to side-job planning;
  - a restructuring option is quoted with the new payment, the new debt load and the extra total interest.
- **Side-job planning:**
  1. Vetting rejects offers with an upfront fee, unrealistic pay, a car requirement when the user has none, or a missing skill.
  2. A greedy fill by pay per hour under slot constraints (weekend days, evenings, flexible) and a per-job maximum, until the target is covered.
- **Scam-message analysis:** weighted indicators — payment to a personal card number, urgency, threats of court or police, SMS-code requests, pay-to-work, unrealistic pay, "approved / no documents / close old loans", Telegram-only recruiter. Two or more indicators give high risk. The message kind is classified as collector, job or loan offer.
- **Restructuring draft:** 12/18/24-month options with payment, monthly saving and total interest. The letter states the extra cost. No personal identifiers are requested.

## 6. LLM providers

| Provider | Model (default) | Notes |
|---|---|---|
| Google Gemini (free tier) | `gemini-3.5-flash-lite`, configurable | OpenAI-compatible endpoint; `reasoning_effort=low`; schemas reduced to Gemini's JSON-schema subset (the server-side validator still enforces the full schema) |
| Anthropic Claude (paid) | `claude-opus-5-5` | Strict tool schemas, effort `medium`, prompt caching of system + tools, server-side refusal fallback |
| Rules engine | — | Regex intent routing (EN/RU/UZ) to the same tools; used when no key is set or on API errors and quota limits |

## 7. Data

- All data is **synthetic**: one user, Jasur, with 3 months of transactions, 3 loans, 4 bills, 4 subscriptions and 6 job offers, 3 of them deliberately harmful. Merchant and platform names are fictional.
- One transaction note carries a prompt-injection string, to test that tool data is treated as data.
- Problem-sizing figures come from public Central Bank of Uzbekistan surveys and Interior Ministry statistics reported by Kun.uz, Gazeta.uz and Daryo.

## 8. Testing and evidence

- **60 automated tests** (pytest, offline, no API spend):
  - the 12 task and 8 attack scenarios at the tool and guard level;
  - the agent loop with scripted fake LLMs for both providers;
  - real SDK request shapes over mock transports;
  - the HTTP API end to end;
  - audit-log tamper detection.
- **Live run:** `scripts/run_live_scenarios.py` runs the 20 scenarios against the live model in fresh sandboxes. It saves transcripts, per-scenario audit logs and a pass/fail summary. **Result on 18 Oct 2026: 20/20 passed** on Gemini 3.5 Flash Lite (free tier), 53 API requests, all audit chains verified (`evidence/live-run-20261018T161742Z/`).
- **Execution evidence:** `/api/audit.jsonl` exports every tool call, guard decision and confirmation as a hash chain that can be verified.

## 9. Deployment

- Docker image, deployed on Render (`render.yaml`).
- The key is stored as a platform secret and never in code.
- Health check: `/healthz`.

## 10. Limitations and roadmap

**Now:**
- sandbox only, no bank or payment APIs;
- in-memory sessions;
- the rate limit is per process;
- scam detection is rule-based;
- the job catalogue is synthetic.

**Pilot path:**
- connect to a bank sandbox API;
- real gig-platform listings through partners;
- a calibrated default-risk model (the team's earlier LightGBM work) to time interventions;
- an Uzbek-language evaluation set;
- a persistent audit store;
- Telegram bot channel.

## 11. Team and tools declaration

**Team:**
- Behzod — product, business case, documentation;
- Sadik — agent and backend;
- Mirkomil — deployment, demo, video.

**AI coding assistants** were used during development. The team reviewed the code and verified it with the test suite.

**Third-party components:** FastAPI, Pydantic, Uvicorn, Anthropic SDK, OpenAI SDK (for Gemini's compatible endpoint). All are open-source licences or official SDKs.
