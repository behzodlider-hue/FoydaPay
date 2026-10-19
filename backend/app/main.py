"""FastAPI app: chat API, confirmations, account state, audit export, and the web chat page."""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel, Field

from typing import Literal

from .agent import Agent
from .sandbox import fmt, make_sandbox_from_profile
from .toolbox import TOOLS, Session, call, confirm, debt_load, expire_pending, rescue_plan

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


class LoanIn(BaseModel):
    label: str = Field(min_length=1, max_length=40)
    lender: str = Field(default="", max_length=40)
    balance: int = Field(ge=100_000, le=10_000_000_000)
    rate: float = Field(ge=0, le=120)  # annual %, as written on the contract
    months: int = Field(ge=1, le=360)


class SubIn(BaseModel):
    key: Literal["music", "video", "video2", "gym", "cloud"]
    used: bool = True


class ProfileIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    name: str = Field(default="", max_length=30)
    income: int = Field(ge=100_000, le=1_000_000_000)
    balance: int = Field(default=0, ge=0, le=1_000_000_000)
    rent: int = Field(default=0, ge=0, le=100_000_000)
    groceries: int = Field(default=0, ge=0, le=100_000_000)
    transport: int = Field(default=0, ge=0, le=100_000_000)
    delivery: int = Field(default=0, ge=0, le=100_000_000)
    cafes: int = Field(default=0, ge=0, le=100_000_000)
    utilities: int = Field(default=0, ge=0, le=100_000_000)
    loans: list[LoanIn] = Field(min_length=1, max_length=5)
    subscriptions: list[SubIn] = Field(default_factory=list, max_length=5)
    weekend_days: int = Field(default=0, ge=0, le=8)
    evenings: int = Field(default=0, ge=0, le=20)
    skills: list[Literal["excel-basic", "smartphone"]] = Field(default_factory=list)
    has_car: bool = False


class ActionIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    tool: str = Field(min_length=3, max_length=40)
    args: dict = Field(default_factory=dict)


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
        "name": sb.name, "custom": sb.custom,
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


@app.post("/api/profile")
def set_profile(body: ProfileIn) -> dict:
    """Mobile quick check: replace the session's sandbox with one built from the user's own answers."""
    s = get_session(body.session_id)
    p = body.model_dump(exclude={"session_id"})
    s.sb = make_sandbox_from_profile(p)
    s.pending = None
    s.messages.clear()  # the agent's earlier context was about the demo account
    s.audit.add("profile", "T0", "allow", {"loans": len(body.loans), "subscriptions": len(body.subscriptions)},
                "sandbox rebuilt from the user's quick-check answers")
    return {"plan": rescue_plan(s.sb), "state": state(s)}


@app.post("/api/action")
def action(body: ActionIn, request: Request) -> dict:
    """Buttons in the mobile app call a tool directly. The same validation, policy guard and audit log apply."""
    rate_limit(request)
    s = get_session(body.session_id)
    if body.tool not in TOOLS:
        raise HTTPException(400, "Unknown action.")
    expire_pending(s)
    out = call(s, body.tool, body.args)
    return {"result": out.content, "is_error": out.is_error, "event": out.event, "state": state(s)}


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


@app.get("/app")
def mobile() -> FileResponse:
    return FileResponse(STATIC / "mobile.html")
