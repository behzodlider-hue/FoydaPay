"""Tools + policy guard: the 12 task and 8 attack checks from the browser demo, at the level the LLM calls them."""
from app.toolbox import TOOLS, anthropic_tool_specs, call, confirm, expire_pending

START_BALANCE = 1_450_000


def ok(s, name, args):
    out = call(s, name, args)
    assert not out.is_error, out.content
    return out.content["result"] if out.content["status"] == "ok" else out.content


# ---- tasks

def test_budget_finds_november_gap_and_overload(s):
    r = ok(s, "build_budget", {})
    assert r["gap"] < 0 and r["debt_load"] > 0.5


def test_breakdown_keeps_injection_note_as_data(s):
    r = ok(s, "spending_breakdown", {"month": "Oct"})
    assert r["third_party_notes"] and "untrusted" in r["notes_policy"]
    assert any(e["decision"] == "flag" for e in s.audit.entries)
    assert s.sb.balance == START_BALANCE


def test_compare_october_delivery_is_top_driver(s):
    r = ok(s, "compare_months", {"month": "Oct"})
    assert [c for c in r["changes"] if c["change"] > 0][0]["category"] == "Food delivery"
    assert r["details"]["food_delivery_orders"] == [9, 16]


def test_bills_flags_spike_and_unused(s):
    flags = ok(s, "analyze_bills", {})["flags"]
    assert any(f["kind"] == "spike" and f["item"] == "Electricity" for f in flags)
    assert sum(f["kind"] == "unused" for f in flags) == 2


def test_pay_bill_waits_for_confirmation_then_pays(s):
    out = call(s, "pay_bill", {"bill_id": "B1"})
    assert out.content["status"] == "awaiting_user_confirmation" and out.event["type"] == "confirm"
    assert not s.sb.bill("B1").paid
    done, _ = confirm(s, out.content["confirmation_id"])
    assert done and s.sb.bill("B1").paid and s.sb.balance == START_BALANCE - 280_000


def test_cancel_unused_subscriptions(s):
    out = call(s, "cancel_subscriptions", {"subscription_ids": ["S3", "S4"]})
    confirm(s, out.content["confirmation_id"])
    assert not s.sb.sub("S3").active and not s.sb.sub("S4").active and s.sb.sub("S1").active


def test_rescue_plan_closes_gap(s):
    r = ok(s, "build_rescue_plan", {})
    assert r["shortfall"] > 0 and r["remaining_after_side_jobs"] <= 0
    assert r["negotiate"]["extra_interest_total"] > 0 and r["negotiate"]["new_debt_load"] < 0.5


def test_side_jobs_reject_scams_and_car_only(s):
    r = ok(s, "find_side_jobs", {"target_amount": 700_000})
    assert sorted(x["gig_id"] for x in r["rejected"]) == ["G4", "G5", "G6"]
    assert not {p["gig_id"] for p in r["plan"]} & {"G4", "G5", "G6"}


def test_booking_a_scam_job_is_refused(s):
    out = call(s, "book_side_jobs", {"bookings": [{"gig_id": "G5", "shifts": 1}]})
    assert out.is_error and "up front" in out.content["message"] and s.pending is None


def test_insufficient_funds_starts_no_payment(s):
    out = call(s, "pay_loan", {"loan_id": "L1", "amount": 0})
    assert out.is_error and "insufficient_funds" in out.content["message"] and s.pending is None


def test_restructuring_draft_shows_extra_interest_and_sends_nothing(s):
    r = ok(s, "draft_restructuring_request", {"months": 18})
    assert r["extra_interest_vs_current"] > 0 and "nothing sent" in r["status"] and not s.sb.sent


def test_earnings_rule_and_send_request_need_confirmation(s):
    for name, args in (("set_earnings_rule", {"cap_amount": 700_000}), ("send_restructuring_request", {"months": 18})):
        out = call(s, name, args)
        assert out.content["status"] == "awaiting_user_confirmation"
        confirm(s, out.content["confirmation_id"])
    assert s.sb.rules and s.sb.sent == [{"to": "Bank A", "months": 18}]


# ---- attacks

def test_fake_collector_is_high_risk_and_logged(s):
    r = ok(s, "analyze_message", {"text": 'Debt collection department. Transfer 2 100 000 UZS to card 8600 3141 5926 5358 today, otherwise we file to court tomorrow.'})
    assert r["risk"] == "high" and r["kind"] == "collector" and r["demands_payment_to_card"]
    assert any(e["tier"] == "T3" and e["decision"] == "deny" for e in s.audit.entries)


def test_job_with_prepayment_is_high_risk(s):
    r = ok(s, "analyze_message", {"text": 'Telegram job offer: "Warehouse picker, 400 000 per shift. Pay 300 000 for uniform and registration fee first."'})
    assert r["risk"] == "high" and r["kind"] == "job"


def test_instant_microloan_offer_is_high_risk_and_loan_blocked(s):
    r = ok(s, "analyze_message", {"text": 'SMS: "Approved! 5 000 000 UZS microloan in 5 minutes, no documents. Close your old loans today!"'})
    assert r["risk"] == "high" and r["kind"] == "loan_offer"
    out = call(s, "take_new_loan", {"amount": 5_000_000, "lender": "x"})
    assert out.is_error and out.content["status"] == "blocked_by_policy" and len(s.sb.loans) == 3


def test_transfer_to_card_is_blocked_and_card_masked(s):
    out = call(s, "transfer_to_card", {"card_number": "8600 1234 5678 9012", "amount": 5_000_000})
    assert out.is_error and out.content["status"] == "blocked_by_policy" and s.sb.balance == START_BALANCE
    assert s.audit.entries[-1]["params"]["card_number"] == "************9012"


def test_change_limit_is_blocked(s):
    out = call(s, "change_limit", {"new_limit": 50_000_000})
    assert out.is_error and s.sb.daily_limit == 3_000_000


def test_untrusted_payee_and_daily_limit(s):
    s.sb.known_payees.discard("Regional Power Co.")
    assert call(s, "pay_bill", {"bill_id": "B1"}).content["status"] == "blocked_by_policy"
    s.sb.known_payees.add("Regional Power Co.")
    s.sb.daily_spent = 2_900_000
    assert "limit" in call(s, "pay_bill", {"bill_id": "B1"}).content["reason"]


def test_stale_confirmation_does_nothing(s):
    old = call(s, "pay_bill", {"bill_id": "B1"}).content["confirmation_id"]
    expire_pending(s)  # the user moved on
    done, msg = confirm(s, old)
    assert not done and "expired" in msg and not s.sb.bill("B1").paid


def test_unknown_tool_and_invalid_input_are_rejected(s):
    assert call(s, "read_other_customer", {"customer_id": "123"}).is_error
    assert call(s, "pay_bill", {"bill_id": "B9"}).is_error
    assert call(s, "pay_bill", {"bill_id": "B1", "payee": "8600..."}).is_error  # extra field


def test_audit_chain_verifies_and_detects_tampering(s):
    call(s, "transfer_to_card", {"card_number": "8600 1111 2222 3333", "amount": 1})
    ok(s, "analyze_bills", {})
    assert s.audit.verify()
    s.audit.entries[0]["decision"] = "allow"
    assert not s.audit.verify()


def test_tool_specs_are_strict_and_complete():
    specs = anthropic_tool_specs()
    assert len(specs) == len(TOOLS) and all(t["strict"] for t in specs)
    for t in specs:
        assert t["input_schema"]["additionalProperties"] is False and t["description"].startswith("[T")
