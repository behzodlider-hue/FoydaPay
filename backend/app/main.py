"""FastAPI app: chat API, confirmations, account state, audit export, and the web chat page."""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from .agent import Agent
from .sandbox import fmt
from .toolbox import Session, confirm, debt_load

app = FastAPI(title="FoydaPay agent", version="0.1.0")
agent = Agent.from_env()

MAX_SESSIONS = 500
SESSION_TTL = 2 * 3600
RATE_LIMIT = 20  # chat requests per minute per IP; protects the LLM budget on a public demo
sessions: "OrderedDict[str, tuple[Session, float]]" = OrderedDict()
hits: dict[str, deque] = defaultdict(deque)
STATIC = Path(__file__).parent / "static"


class ChatIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    message: str = Field(min_length=1, max_length=1000)


class ConfirmIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    confirmation_id: str = Field(min_length=3, max_length=32)
    approve: bool = True


def get_session(sid: str) -> Session:
    now = time.time()
    for k in [k for k, (_, t) in sessions.items() if now - t > SESSION_TTL]:
        sessions.pop(k, None)
    if sid not in sessions:
        raise HTTPException(404, "Session not found or expired. Start a new one.")
    s, _ = sessions[sid]
    sessions[sid] = (s, now)
    sessions.move_to_end(sid)
    return s


def rate_limit(request: Request) -> None:
    ip = request.client.host if request.client else "unknown"
    q, now = hits[ip], time.time()
    while q and now - q[0] > 60:
        q.popleft()
    if len(q) >= RATE_LIMIT:
        raise HTTPException(429, "Too many messages. Wait a minute and try again.")
    q.append(now)


def state(s: Session) -> dict:
    sb, d = s.sb, debt_load(s.sb)
    return {
        "card_balance": fmt(sb.balance), "income": fmt(sb.income), "loan_payments": fmt(d["total"]),
        "debt_load": round(d["dti"], 3), "agent_payments_today": f"{fmt(sb.daily_spent)} / {fmt(sb.daily_limit)}",
        "loans": [{"label": l.label, "rate": l.rate, "months": l.months, "payment": fmt(l.payment)} for l in sb.loans],
        "subscriptions": [{"name": x.name, "amount": fmt(x.amount), "active": x.active, "unused": x.unused_days > 30} for x in sb.subs],
        "bills": [{"name": b.name, "amount": fmt(b.amount), "paid": b.paid} for b in sb.bills],
        "booked": sb.booked, "rules": sb.rules, "sent": sb.sent,
        "pending": {"id": s.pending.id, "summary": s.pending.summary} if s.pending else None,
        "audit_tail": s.audit.entries[-15:][::-1], "audit_chain_ok": s.audit.verify(),
    }


@app.get("/healthz")
def healthz() -> dict:
    return {"ok": True, "mode": "llm" if agent.client else "rules",
            "provider": agent.provider if agent.client else None, "model": agent.model if agent.client else None}


@app.post("/api/session")
def new_session() -> dict:
    while len(sessions) >= MAX_SESSIONS:
        sessions.popitem(last=False)
    sid = secrets.token_urlsafe(16)
    sessions[sid] = (Session(), time.time())
    return {"session_id": sid, "state": state(sessions[sid][0])}


@app.post("/api/chat")
def chat(body: ChatIn, request: Request) -> dict:
    rate_limit(request)
    s = get_session(body.session_id)
    reply = agent.handle(s, body.message)
    return {"reply": reply.text, "events": reply.events, "mode": reply.mode, "state": state(s)}


@app.post("/api/confirm")
def confirm_action(body: ConfirmIn) -> dict:
    s = get_session(body.session_id)
    ok, msg = confirm(s, body.confirmation_id, body.approve)
    return {"ok": ok, "reply": msg, "state": state(s)}


@app.get("/api/state")
def get_state(session_id: str) -> dict:
    return state(get_session(session_id))


@app.get("/api/audit.jsonl", response_class=PlainTextResponse)
def audit_export(session_id: str) -> str:
    """Execution evidence: every tool call, decision and confirmation, hash-chained."""
    return get_session(session_id).audit.jsonl()


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")
