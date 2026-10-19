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


V2 = {**PROFILE, "income": 3_500_000, "delivery": 200_000, "cafes": 100_000, "other": 400_000, "payday": 10,
      "loans": [{**PROFILE["loans"][0], "due_day": 5}, {**PROFILE["loans"][1], "due_day": 20}],
      "subscriptions": [{"key": "music", "used": True}, {"key": "other", "used": False, "name": "Game pass", "amount": 45_000}],
      "weekend_days": 0, "evenings": 0, "hours_per_week": 3, "formats": ["online", "alternate_odd"], "skills": [],
      "skills_note": "I can teach English"}


def test_other_spending_formats_and_free_text_skills():
    sb = make_sandbox_from_profile(V2)
    p = rescue_plan(sb)
    assert "languages" in sb.skills and sb.hours_cap == 12 and sb.loans[0].due_day == 5
    assert any("Game pass" in c["what"] for c in p["cut"]["items"])  # the user's own unused subscription
    assert {c["code"] for c in p["cut"]["items"]} >= {"cancel_sub", "cut_other"}
    assert any(a["code"] == "other_share" for a in p["advice"])
    assert p["earn"]["plan"] == [] and p["earn"]["rejected"] == []  # real users get real vacancies, not the demo catalog


def test_vacancies_endpoint_uses_region_and_skills(monkeypatch):
    from app import jobs
    seen = []

    def fake_fetch(region, query):
        seen.append((region, query))
        return [jobs.normalize({"id": len(seen), "company_name": "Test LLC", "position_name": "Tarjimon",
                                "position_name_ru": query.title(), "position_salary": "2000000.00", "position_rate": "1.00",
                                "company_soato_code4": region, "date_start": "2026-10-01"})]
    monkeypatch.setattr(jobs, "_fetch", fake_fetch)
    c = TestClient(app)
    sid = c.post("/api/session").json()["session_id"]
    c.post("/api/profile", json={"session_id": sid, **V2, "region": "1718", "lang": "uz", "work_status": "employed"})
    r = c.post("/api/jobs", json={"session_id": sid}).json()
    assert {q for _, q in seen} == {"переводчик", "преподаватель"} and all(reg == "1718" for reg, _ in seen)
    assert r["region"] == "Samarkand" and r["vacancies"][0]["url"].startswith("https://ish.mehnat.uz/vacancies/")
    assert "hh.uz/search/vacancy" in r["more"]["hh"]
    st = c.get(f"/api/state?session_id={sid}").json()
    assert any(e["tool"] == "search_vacancies" for e in st["audit_tail"])  # audited like every other tool


def test_letter_follows_app_language_and_scam_codes():
    from app.toolbox import Session as S, analyze_message_core
    s = S()
    s.sb = make_sandbox_from_profile({**V2, "lang": "ru"})
    letter = call(s, "draft_restructuring_request", {"months": 18}).content["result"]["letter"]
    assert letter.startswith("Кому: MFO X")
    r = analyze_message_core("Debt collection: transfer to card 8600 3141 5926 5358 today or court.")
    assert {"card", "urgency", "threat"} <= set(r["reason_codes"])


def test_security_summary_chat_reset_and_validation():
    c = TestClient(app)
    sid = c.post("/api/session").json()["session_id"]
    assert c.post("/api/profile", json={"session_id": sid, **V2}).status_code == 200
    st = c.post("/api/action", json={"session_id": sid, "tool": "transfer_to_card", "args": {"card_number": "8600111122223333", "amount": 5}}).json()["state"]
    ev = st["security"]["events"][0]
    assert st["security"]["attacks"] == 1 and ev["kind"] == "transfer_to_card" and st["security"]["log_intact"]
    hist = [{"role": "assistant", "text": "Hi"}, {"role": "user", "text": "Where does my money go?"},
            {"role": "assistant", "text": "Mostly rent."}, {"role": "user", "text": "unanswered"}]
    assert c.post("/api/chat/reset", json={"session_id": sid, "history": hist}).json()["turns"] == 2  # starts with the user, ends answered
    assert c.post("/api/chat/reset", json={"session_id": sid}).json()["turns"] == 0
    bad = {**V2, "subscriptions": [{"key": "other", "used": True, "name": "X"}]}
    assert c.post("/api/profile", json={"session_id": sid, **bad}).status_code == 422  # "other" needs a price
