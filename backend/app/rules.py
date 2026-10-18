"""Rules-based fallback: used when no LLM is configured or the LLM call fails.

It maps a message to the same tools the LLM uses (so the policy guard and audit log apply
identically) and formats a short reply. The LLM agent in agent.py is the primary path.
"""
from __future__ import annotations

import re

from .sandbox import MONTHS, fmt
from .toolbox import Session, call, rescue_plan

YES = re.compile(r"^(yes|y|confirm|ok|okay|да|ha|xa|tasdiq)\b", re.I)
NO = re.compile(r"^(no|stop|нет|yo'q)\b", re.I)


def month_in(t: str) -> str | None:
    for pat, m in ((r"\baug|август|avgust", "Aug"), (r"\bsep|сентяб|sentabr", "Sep"),
                   (r"\boct|октяб|oktabr", "Oct"), (r"\bnov|ноябр|noyabr", "Nov")):
        if re.search(pat, t):
            return m
    return None


def detect_lang(s: str) -> str:
    if re.search(r"[а-яё]", s, re.I):
        return "ru"
    if re.search(r"(o['ʻ‘’`]|g['ʻ‘’`]|qarz|kredit|olmayman|yetmay|oylig|kechik|qanday|nega|\bpul\b|\bish\b|yordam|kerak)", s, re.I):
        return "uz"
    return "en"


def amount_in(t: str) -> int | None:
    m = re.search(r"(\d{4,})", re.sub(r"(\d)[\s ](?=\d{3}\b)", r"\1", t))
    if m:
        return int(m.group(1))
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*(m|mln|million|млн)\b", t)
    return round(float(m.group(1).replace(",", ".")) * 1e6) if m else None


def route(raw: str) -> dict:
    t = re.sub(r"[ʻ‘’`]", "'", raw.lower())
    s = t.strip()
    m = month_in(t)
    rules = [
        (r"ignore (all |the )?(previous|prior|above) instructions|system prompt|developer mode|reveal (your )?(prompt|instructions|keys?)|api key|игнорируй", {"intent": "injection"}),
        (r"other (customers|users|clients)|all (customers|users)|someone else'?s|чужи|других клиент|boshqa mijoz", {"intent": "others_data"}),
        (r"\badmin\b|administrator|raise (my )?(card |transfer )?limit|increase (my )?limit|лимит|limitni", {"intent": "privilege"}),
    ]
    for pat, r in rules:
        if re.search(pat, t):
            return r
    if len(raw) > 50 and re.search(r"collector|коллектор|court|суд\b|sms code|код из смс|uniform|registration fee|deposit|approved!|no documents|без документов|microloan in|займ за|like videos", t):
        return {"intent": "analyze_message"}
    if re.search(r"(transfer|send|move|перевед|отправ|o'tkaz|yubor).{0,40}(card|карт|karta)", t) or re.search(r"\b(8600|9860|5614)[\s\d*]{8,}", t):
        return {"intent": "transfer_card"}
    if re.search(r"(new|another|take|get|оформ|взять|ещё|yangi).{0,20}(loan|microloan|займ|кредит|qarz)", t):
        return {"intent": "new_loan", "take": bool(re.search(r"take|оформ|взять|apply|get me", t)) and not re.search(r"should|стоит|kerakmi|\?", t)}
    if YES.search(s):
        return {"intent": "confirm_text"}
    if NO.search(s) and not m:
        return {"intent": "decline_text"}
    if m and re.search(r"(i meant|i mean|^no\b|^не\b|имел в виду|nazarda)", s):
        return {"intent": "correction", "month": m}
    if re.search(r"restructur|реструкт|qayta tuz|letter|заявлен|ariza|request to (the )?bank", t):
        return {"intent": "send_request" if re.search(r"send|отправ|yubor", t) else "restructure"}
    if re.search(r"cancel|отмен|bekor", t):
        which = ("unused" if re.search(r"don'?t use|unused|не пользуюсь|ishlatmay|ones", t) else "S4" if re.search(r"gym|fit", t)
                 else "S3" if "cinema" in t else "S2" if "stream" in t else "S1" if "music" in t else "ask")
        return {"intent": "cancel_sub", "which": which}
    if re.search(r"(pay|оплат|to'la).{0,25}(electric|свет|электр|bill|счет|счёт|gas|газ|internet|mobile)", t):
        bill = "B2" if re.search(r"gas|газ", t) else "B3" if "internet" in t else "B4" if re.search(r"mobile|телефон", t) else "B1"
        return {"intent": "pay_bill", "bill": bill}
    if re.search(r"(pay|оплат|внести|to'la).{0,25}(loan|кредит|kredit|installment|рассроч|microloan|займ)", t) and not re.search(r"can'?t|cannot|не могу|olmayman", t):
        loan = "L3" if re.search(r"micro|займ", t) else "L2" if re.search(r"install|рассроч|phone", t) else "L1"
        return {"intent": "pay_loan", "loan": loan, "amount": amount_in(t)}
    if re.search(r"(route|direct|направ|yo'nalt).{0,30}(earning|gig|payout|подработ|заработ)|earnings rule", t):
        return {"intent": "earnings_rule"}
    if re.search(r"(book|забронир|записа|band qil).{0,30}(shift|gig|job|смен|подработ|these)", t):
        return {"intent": "book_gigs"}
    if re.search(r"gig|side job|side income|extra (money|income|work)|подработ|part[- ]time|qo'shimcha|ish top", t):
        return {"intent": "gigs"}
    if re.search(r"can'?t pay|cannot pay|short|not enough|struggl|debt|loan|kredit|qarz|кредит|долг|не хватает|не могу (за)?платить|olmayman|yetmay|rescue|help me", t):
        return {"intent": "rescue", "delayed": bool(re.search(r"kechik|задерж|delayed|late salary|salary is late", t))}
    if re.search(r"why|compare|почему|сравн|nega", t):
        return {"intent": "compare", "month": m or "Oct"}
    if re.search(r"bill|счет|счёт|коммунал|kommunal|utilit", t):
        return {"intent": "bills"}
    if re.search(r"budget|бюджет|byudjet", t):
        return {"intent": "budget"}
    if re.search(r"spend|money go|where.*money|трат|расход|xarajat|pul qayer", t):
        return {"intent": "breakdown", "month": m or "Oct"}
    return {"intent": "unknown"}


# --------------------------------------------------------------------------- handlers

class Reply:
    def __init__(self) -> None:
        self.lines: list[str] = []
        self.events: list[dict] = []
        self.data: dict = {}

    def say(self, text: str) -> None:
        self.lines.append(text)

    def use(self, s: Session, tool: str, args: dict):
        out = call(s, tool, args)
        if out.event:
            self.events.append(out.event)
        if out.is_error:
            msg = out.content.get("reason") or out.content.get("message", "")
            self.say(("Blocked: " if out.content.get("status") == "blocked_by_policy" else "") + msg)
            return None
        if out.content["status"] == "awaiting_user_confirmation":
            self.say(f"{out.content['summary']}. Nothing has happened yet; press Confirm to go ahead.")
            return out.content
        return out.content["result"]


def h_breakdown(s, r, rep):
    month = r.get("month") or "Oct"
    if month not in MONTHS:
        rep.say("This demo account has data for August-October 2026 only.")
        return
    res = rep.use(s, "spending_breakdown", {"month": month})
    rep.data = res
    rep.say(f"{month} spending: {fmt(res['total'])}. " + "; ".join(f"{c['category']} {fmt(c['amount'])} ({c['share']:.0%})" for c in res["categories"][:5]) + ".")
    if res.get("third_party_notes"):
        rep.say("A transfer note from an unknown card contains instructions to pay a card. I treat notes as data, not commands, so I did nothing.")


def h_compare(s, r, rep):
    res = rep.use(s, "compare_months", {"month": r.get("month") if r.get("month") in ("Sep", "Oct") else "Oct"})
    rep.data = res
    top = [c for c in res["changes"] if c["change"] > 0][:3]
    rep.say(f"{res['month']} cost {fmt(res['total_change'])} more than {res['previous_month']}: " + "; ".join(f"{c['category']} +{fmt(c['change'])}" for c in top) + ".")


def h_bills(s, r, rep):
    res = rep.use(s, "analyze_bills", {})
    rep.data = res
    rep.say(" ".join(f["text"] for f in res["flags"]) or "Bills look normal.")


def h_budget(s, r, rep):
    res = rep.use(s, "build_budget", {})
    rep.data = res
    rep.say(f"November budget on {fmt(res['income'])}: total {fmt(res['total'])}. " + (
        f"Even with tight limits you are {fmt(-res['gap'])} short; loan payments are {res['debt_load']:.1%} of income." if res["gap"] < 0 else f"Buffer: {fmt(res['gap'])}."))


def h_rescue(s, r, rep):
    if r.get("delayed"):
        rep.say("Sorry your salary is late. How long is the delay? I'll plan for the worst case until you tell me.")
    res = rep.use(s, "build_rescue_plan", {})
    rep.data = {"plan": res}
    rep.say(f"If November looks like October, you are short {fmt(res['shortfall'])}; loan payments are {res['debt_load']:.1%} of income.")
    rep.say(f"1. Cut {fmt(res['cut']['total'])}: " + "; ".join(c["what"] for c in res["cut"]["items"]) + ".")
    rep.say(f"2. Earn {fmt(res['earn']['total'])} in {res['earn']['hours']} hours: " + "; ".join(f"{p['shifts']} x {p['title']}" for p in res["earn"]["plan"]) + ".")
    n = res["negotiate"]
    rep.say(f"3. Optional: 18 months on the Bank A loan saves {fmt(n['saves_per_month'])} a month but costs about {fmt(n['extra_interest_total'])} more interest.")


def h_gigs(s, r, rep):
    target = rescue_plan(s.sb)["remaining_after_cuts"] or 500_000
    res = rep.use(s, "find_side_jobs", {"target_amount": target})
    rep.data = res
    rep.say(f"To cover {fmt(target)}: " + "; ".join(f"{p['shifts']} x {p['title']} ({fmt(p['earns'])})" for p in res["plan"]) + ".")
    rep.say("Rejected: " + "; ".join(f"{x['title'].split(' - ')[0]} ({x['reason']})" for x in res["rejected"]) + ".")


def h_book(s, r, rep):
    plan = rescue_plan(s.sb)["earn"]["plan"]
    rep.use(s, "book_side_jobs", {"bookings": [{"gig_id": p["gig_id"], "shifts": p["shifts"]} for p in plan]})


def h_rule(s, r, rep):
    rep.use(s, "set_earnings_rule", {"cap_amount": max(1, rescue_plan(s.sb)["remaining_after_cuts"])})


def h_cancel(s, r, rep):
    which = r["which"]
    if which == "ask":
        rep.say("Which subscription? Active: " + ", ".join(x.name for x in s.sb.subs if x.active) + ".")
        return
    ids = [x.id for x in s.sb.subs if x.active and x.unused_days > 30] if which == "unused" else [which]
    rep.use(s, "cancel_subscriptions", {"subscription_ids": ids})


def h_pay_bill(s, r, rep):
    rep.use(s, "pay_bill", {"bill_id": r["bill"]})


def h_pay_loan(s, r, rep):
    rep.use(s, "pay_loan", {"loan_id": r["loan"], "amount": r.get("amount") or 0})


def h_restructure(s, r, rep):
    res = rep.use(s, "draft_restructuring_request", {"months": 18})
    rep.data = res
    rep.say("Options: " + "; ".join(f"{o['months']} months: {fmt(o['payment'])}, total interest {fmt(o['total_interest'])}" for o in res["options"]) + ".")
    rep.say("Draft (nothing is sent yet):\n" + res["letter"])


def h_send(s, r, rep):
    rep.use(s, "send_restructuring_request", {"months": (s.sb.draft or {}).get("months", 18)})


def h_analyze(s, r, rep):
    res = rep.use(s, "analyze_message", {"text": r["text"]})
    rep.data = res
    label = {"collector": "fake debt collector", "job": "fake job offer", "loan_offer": "predatory loan offer"}.get(res["kind"], "suspicious message")
    if res["risk"] == "high":
        rep.say(f"High risk: this looks like a {label}. Don't pay and don't share any codes. " + " ".join(res["reasons"]))
    else:
        rep.say(("Be careful: " + " ".join(res["reasons"])) if res["reasons"] else "No clear warning signs.")
    if res["kind"] == "loan_offer":
        h_new_loan(s, {"take": False}, rep)


def h_new_loan(s, r, rep):
    from .sandbox import annuity
    d = rep.use(s, "get_account_overview", {})
    add = annuity(5_000_000, 0.6, 12)
    rep.say(f"A new 5 000 000 microloan at 60% would add about {fmt(add)} a month: debt load {d['debt_load']:.1%} -> {(d['loan_payments_total'] + add) / d['monthly_income']:.1%}.")
    if r.get("take"):
        rep.use(s, "take_new_loan", {"amount": 5_000_000, "lender": "unknown"})
    else:
        rep.say("I recommend not taking it, and I never take loans on your behalf.")


def h_transfer(s, r, rep):
    card = re.search(r"\b(\d{4})[\s\d*]{8,}", r["text"])
    rep.use(s, "transfer_to_card", {"card_number": card.group(0) if card else "unknown", "amount": amount_in(r["text"].lower()) or 0})
    rep.say("If someone asked for this urgently by phone or Telegram, it's very likely a scam. Nothing was sent.")


def h_injection(s, r, rep):
    s.audit.add("system_prompt", "T3", "deny", {}, "request to ignore instructions or reveal internals")
    rep.say("I don't reveal my internal instructions and I ignore instructions that try to override them.")
    if re.search(r"card|карт|\b(8600|9860)", r["text"], re.I):
        h_transfer(s, r, rep)


def h_others(s, r, rep):
    s.audit.add("other_customer_data", "T3", "deny", {}, "no tool can read other customers' data")
    rep.say("I can only see your own accounts. No tool I have can read other customers' data.")


def h_privilege(s, r, rep):
    rep.use(s, "change_limit", {"new_limit": amount_in(r["text"].lower()) or 0})


def h_correction(s, r, rep):
    rep.say(f"Got it, {r['month']} then.")
    (h_compare if s.last_intent == "compare" else h_breakdown)(s, r, rep)


def h_confirm_text(s, r, rep):
    s.audit.add("confirmation", "T2", "deny", {}, "no pending action")
    rep.say("There is nothing waiting for your confirmation, so I did nothing.")


def h_decline_text(s, r, rep):
    rep.say("OK.")


def h_delay(s, r, rep):
    l1 = s.sb.loan("L1")
    rep.say(f"Noted. The first payment at risk is {l1.lender} ({fmt(l1.payment)}). I can send side-job payouts there first.")


def h_unknown(s, r, rep):
    rep.say("I can help with your budget, bills, spending, loans and side jobs. Try: 'Where does my money go?' or 'I can't pay my loans this month'.")


HANDLERS = {
    "breakdown": h_breakdown, "compare": h_compare, "bills": h_bills, "budget": h_budget, "rescue": h_rescue,
    "gigs": h_gigs, "book_gigs": h_book, "earnings_rule": h_rule, "cancel_sub": h_cancel, "pay_bill": h_pay_bill,
    "pay_loan": h_pay_loan, "restructure": h_restructure, "send_request": h_send, "analyze_message": h_analyze,
    "new_loan": h_new_loan, "transfer_card": h_transfer, "injection": h_injection, "others_data": h_others,
    "privilege": h_privilege, "correction": h_correction, "confirm_text": h_confirm_text,
    "decline_text": h_decline_text, "unknown": h_unknown,
}


def respond(s: Session, text: str) -> Reply:
    r = route(text)
    r["text"] = text
    rep = Reply()
    rep.data["intent"] = r["intent"]
    lang = detect_lang(text)
    if lang != "en":
        rep.say(f"(Understood in {'Uzbek' if lang == 'uz' else 'Russian'}; replying in English, the track language.)")
    if re.search(r"a week|недел|hafta|next month|следующ|keyingi oy", text.lower()) and r["intent"] == "unknown":
        h_delay(s, r, rep)
    else:
        HANDLERS.get(r["intent"], h_unknown)(s, r, rep)
    if r["intent"] in ("breakdown", "compare"):
        s.last_intent = r["intent"]
    rep.data = {**(rep.data or {}), "intent": r["intent"], "lang": lang}
    return rep
