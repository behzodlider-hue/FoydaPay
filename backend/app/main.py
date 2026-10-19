"""FastAPI app: chat API, confirmations, account state, audit export, and the web chat page."""
from __future__ import annotations

import secrets
import time
from collections import OrderedDict, defaultdict, deque
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, model_validator

from typing import Literal

from . import jobs
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
    due_day: int = Field(default=0, ge=0, le=31)  # 0 = not given


class SubIn(BaseModel):
    key: Literal["music", "video", "video2", "gym", "cloud", "other"]
    used: bool = True
    name: str = Field(default="", max_length=30)  # for "other": what the user pays for
    amount: int = Field(default=0, ge=0, le=10_000_000)  # for "other"; catalog items have a typical price

    @model_validator(mode="after")
    def other_needs_amount(self):
        if self.key == "other" and self.amount < 1000:
            raise ValueError("An 'other' subscription needs its monthly price.")
        return self


class ProfileIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    name: str = Field(default="", max_length=30)
    income: int = Field(ge=100_000, le=1_000_000_000)
    payday: int = Field(default=25, ge=1, le=31)
    balance: int = Field(default=0, ge=0, le=1_000_000_000)
    rent: int = Field(default=0, ge=0, le=100_000_000)
    groceries: int = Field(default=0, ge=0, le=100_000_000)
    transport: int = Field(default=0, ge=0, le=100_000_000)
    delivery: int = Field(default=0, ge=0, le=100_000_000)
    cafes: int = Field(default=0, ge=0, le=100_000_000)
    utilities: int = Field(default=0, ge=0, le=100_000_000)
    other: int = Field(default=0, ge=0, le=100_000_000)
    loans: list[LoanIn] = Field(min_length=1, max_length=5)
    subscriptions: list[SubIn] = Field(default_factory=list, max_length=5)
    weekend_days: int = Field(default=0, ge=0, le=8)
    evenings: int = Field(default=0, ge=0, le=20)
    hours_per_week: int = Field(default=0, ge=0, le=60)  # 0 = no cap
    formats: list[Literal["day", "alternate_even", "alternate_odd", "evening", "night", "online"]] = Field(default_factory=list, max_length=6)
    skills: list[Literal["excel-basic", "smartphone", "languages", "design"]] = Field(default_factory=list, max_length=4)
    skills_note: str = Field(default="", max_length=200)
    has_car: bool = False
    # From the onboarding screen. Name and gender stay on the phone; these help find vacancies and word the advice.
    lang: Literal["en", "ru", "uz"] = "en"
    region: str = Field(default="1726", pattern=r"^\d{4}$")
    age: int | None = Field(default=None, ge=14, le=100)
    education: Literal["school", "college", "bachelor", "master", ""] = ""
    work_status: Literal["employed", "self_employed", "student", "unemployed", "retired", ""] = ""


class VacancyIn(BaseModel):
    """One vacancy the phone fetched from ishapi.mehnat.uz. Checked again here: only official vacancy links are accepted."""
    id: int = Field(ge=1)
    title: str = Field(default="", max_length=120)
    title_uz: str = Field(default="", max_length=120)
    company: str = Field(default="", max_length=120)
    salary: int = Field(default=0, ge=0, le=1_000_000_000)
    rate: float = Field(default=1.0, ge=0, le=5)
    region_code: str = Field(default="", pattern=r"^\d{0,7}$")
    posted: str | None = Field(default=None, max_length=10)


class JobsIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    query: str = Field(default="", max_length=40)
    fetch: bool = True  # False: only the search plan, the phone queries the database itself
    found: list[VacancyIn] | None = Field(default=None, max_length=30)


class ActionIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    tool: str = Field(min_length=3, max_length=40)
    args: dict = Field(default_factory=dict)


class Turn(BaseModel):
    role: Literal["user", "assistant"]
    text: str = Field(min_length=1, max_length=4000)


class ChatResetIn(BaseModel):
    session_id: str = Field(min_length=8, max_length=64)
    history: list[Turn] = Field(default_factory=list, max_length=40)  # an older chat the user reopened


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


# Plain-language lines for the Security screen, one per kind of blocked or flagged event in the audit log.
SECURITY_TEXT = {
    "transfer_to_card": "Someone asked to send your money to an unknown card. FoydaPay blocked it.",
    "take_new_loan": "Someone asked to take a new loan in your name. FoydaPay blocked it.",
    "change_limit": "Someone tried to change your payment limits. FoydaPay blocked it.",
    "spending_breakdown": "A transfer note contained hidden instructions to pay a card. FoydaPay ignored them.",
    "analyze_message": "A message you checked asked for money on a personal card. That is a common scam.",
    "book_side_jobs": "A job offer asked you to pay first. FoydaPay refused to book it.",
}


def security(s: Session) -> dict:
    events = []
    for e in s.audit.entries:
        if e["decision"] not in ("deny", "flag") or e["tool"] == "confirmation":
            continue
        kind, text = e["tool"], SECURITY_TEXT.get(e["tool"])
        if not text and "trusted payee" in e["reason"]:
            kind, text = "untrusted_payee", "A payment to a recipient you never paid before was stopped."
        if text:  # kind lets the phone app show the line in the user's language
            events.append({"at": e["ts"], "kind": kind, "text": text, "level": "blocked" if e["decision"] == "deny" else "ignored"})
    return {"attacks": len(events), "events": events[-10:][::-1], "log_intact": s.audit.verify()}


def state(s: Session) -> dict:
    sb, d = s.sb, debt_load(s.sb)
    return {
        "name": sb.name, "custom": sb.custom, "payday": sb.payday, "income_raw": sb.income,
        "card_balance": fmt(sb.balance), "income": fmt(sb.income), "loan_payments": fmt(d["total"]),
        "debt_load": round(d["dti"], 3), "agent_payments_today": f"{fmt(sb.daily_spent)} / {fmt(sb.daily_limit)}",
        "loans": [{"label": l.label, "lender": l.lender, "rate": l.rate, "months": l.months, "payment": fmt(l.payment),
                   "payment_raw": round(l.payment), "balance": round(l.balance), "due_day": l.due_day} for l in sb.loans],
        "subscriptions": [{"name": x.name, "amount": fmt(x.amount), "active": x.active, "unused": x.unused_days > 30} for x in sb.subs],
        "bills": [{"name": b.name, "amount": fmt(b.amount), "paid": b.paid} for b in sb.bills],
        "booked": sb.booked, "rules": sb.rules, "sent": sb.sent,
        "pending": {"id": s.pending.id, "summary": s.pending.summary} if s.pending else None,
        "audit_tail": s.audit.entries[-15:][::-1], "audit_chain_ok": s.audit.verify(), "security": security(s),
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


@app.post("/api/chat/reset")
def chat_reset(body: ChatResetIn) -> dict:
    """New chat (empty history), or an older chat reopened from the phone: its text turns become the agent's context."""
    s = get_session(body.session_id)
    expire_pending(s)
    msgs: list[dict] = []
    for t in body.history:
        if not msgs and t.role != "user":
            continue  # the conversation must start with the user
        if msgs and msgs[-1]["role"] == t.role:
            msgs[-1]["content"] += "\n" + t.text
        else:
            msgs.append({"role": t.role, "content": t.text})
    if msgs and msgs[-1]["role"] == "user":
        msgs.pop()  # an unanswered question is asked again by the next message
    s.messages[:] = msgs
    return {"ok": True, "turns": len(msgs)}


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


@app.post("/api/jobs")
def find_jobs(body: JobsIn, request: Request) -> dict:
    """Real vacancies for the user's region and skills (National Vacancy Database). Goes through the guard and audit log."""
    rate_limit(request)
    s = get_session(body.session_id)
    sb = s.sb
    skills = list(sb.skills) if sb.custom else ["smartphone", "excel-basic"]
    if body.found is not None:  # results the phone fetched: keep them for the agent and return them in the usual shape
        rows = [{**v.model_dump(), "region": jobs.REGIONS.get(v.region_code[:4], ""), "url": f"{jobs.SITE}/vacancies/{v.id}"} for v in body.found]
        sb.jobs_found = rows
        s.audit.add("search_vacancies", "T0", "allow", {"source": "phone", "count": len(rows)}, "vacancies fetched by the user's phone")
        return jobs.result(sb.region if sb.region in jobs.REGIONS else None, jobs.queries_for(skills, sb.has_car, body.query), rows)
    if not body.fetch:
        return jobs.search(sb.region, skills, sb.has_car, body.query, fetch=False)
    out = call(s, "search_vacancies", {"query": body.query} if body.query else {})
    if out.is_error:
        raise HTTPException(502, "The vacancy database did not answer. Try again in a minute.")
    return out.content["result"]


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


# Scripts of the mobile app (/static/*.js) and the tour's voice-over (/static/tour/<lang>/<step>.mp3)
app.mount("/static", StaticFiles(directory=STATIC), name="static")
