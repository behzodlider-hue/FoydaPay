"""Mobile app API: a sandbox built from the user's own quick-check answers, and buttons that call tools through the guard."""
from fastapi.testclient import TestClient

from app.main import app
from app.sandbox import make_sandbox_from_profile
from app.toolbox import Session, call, rescue_plan

PROFILE = {
    "name": "Dilnoza", "income": 4_000_000, "balance": 600_000, "rent": 1_000_000, "groceries": 900_000, "transport": 200_000,
    "delivery": 400_000, "cafes": 150_000, "utilities": 300_000,
    "loans": [{"label": "Microloan", "lender": "MFO X", "balance": 6_000_000, "rate": 56, "months": 10},
              {"label": "Installment (nasiya)", "lender": "Shop Y", "balance": 2_400_000, "rate": 0, "months": 6}],
    "subscriptions": [{"key": "music", "used": True}, {"key": "gym", "used": False}],
    "weekend_days": 4, "evenings": 2, "skills": ["smartphone"], "has_car": False,
}


def test_profile_sandbox_drives_the_plan():
    sb = make_sandbox_from_profile(PROFILE)
    p = rescue_plan(sb)
    assert sb.custom and sb.rent == 1_000_000 and len(sb.loans) == 2
    assert 0.28 < p["debt_load"] < 0.30 and p["shortfall"] > 0  # 1.16M of loan payments on 4M income
    assert any("Gym" in c["what"] for c in p["cut"]["items"])  # unused subscription offered as a cut
    assert p["negotiate"]["lender"] == "MFO X"  # the interest-bearing loan, not the 0% installment
    assert not {j["gig_id"] for j in p["earn"]["plan"]} & {"G3", "G4", "G5", "G6"}  # no Excel, no car, no scams


def test_profile_payees_and_guard():
    s = Session()
    s.sb = make_sandbox_from_profile(PROFILE)
    out = call(s, "pay_loan", {"loan_id": "L2", "amount": 0})
    assert out.content["status"] == "awaiting_user_confirmation"  # the user's own lender is a trusted payee
    assert call(s, "transfer_to_card", {"card_number": "8600123412341234", "amount": 1}).content["status"] == "blocked_by_policy"


def test_profile_and_action_endpoints():
    c = TestClient(app)
    sid = c.post("/api/session").json()["session_id"]
    r = c.post("/api/profile", json={"session_id": sid, **PROFILE})
    assert r.status_code == 200 and r.json()["state"]["custom"] and r.json()["plan"]["shortfall"] > 0
    r = c.post("/api/action", json={"session_id": sid, "tool": "cancel_subscriptions", "args": {"subscription_ids": ["S2"]}}).json()
    assert r["event"]["type"] == "confirm"
    ok = c.post("/api/confirm", json={"session_id": sid, "confirmation_id": r["event"]["id"]}).json()
    assert ok["ok"] and not ok["state"]["subscriptions"][1]["active"]
    r = c.post("/api/action", json={"session_id": sid, "tool": "transfer_to_card", "args": {"card_number": "8600111122223333", "amount": 5}}).json()
    assert r["is_error"] and r["result"]["status"] == "blocked_by_policy"
    r = c.post("/api/action", json={"session_id": sid, "tool": "analyze_message",
                                    "args": {"text": "Debt collection: transfer to card 8600 3141 5926 5358 today or court."}}).json()
    assert r["result"]["result"]["risk"] == "high"
    assert c.post("/api/action", json={"session_id": sid, "tool": "rm_rf", "args": {}}).status_code == 400


def test_profile_validation():
    c = TestClient(app)
    sid = c.post("/api/session").json()["session_id"]
    bad = {**PROFILE, "loans": []}
    assert c.post("/api/profile", json={"session_id": sid, **bad}).status_code == 422
    assert c.post("/api/profile", json={"session_id": sid, **PROFILE, "income": 5}).status_code == 422
    assert c.get("/app").status_code == 200
