"""Agent loop with a scripted fake Claude client: tool_use handling, guard, refusal, failures, typed confirmations."""
from types import SimpleNamespace as NS

import anthropic
import httpx2
import pytest

from app.agent import Agent


def tool_use(name, inp, id_="tu_1"):
    return NS(type="tool_use", id=id_, name=name, input=inp)


def text(t):
    return NS(type="text", text=t)


class FakeClient:
    """Mimics client.beta.messages.create / client.messages.create and returns scripted responses."""

    def __init__(self, script):
        self.script, self.calls = list(script), []
        self.messages = NS(create=self._create)
        self.beta = NS(messages=NS(create=self._create))

    def _create(self, **kw):
        self.calls.append({**kw, "messages": list(kw["messages"])})  # snapshot: the agent keeps appending
        item = self.script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def resp(stop, *content):
    return NS(stop_reason=stop, content=list(content))


def tool_results(kw):
    return kw["messages"][-1]["content"]


def test_request_shape_uses_opus_tools_and_fallbacks(s):
    fake = FakeClient([resp("end_turn", text("Hi"))])
    Agent(fake).handle(s, "hello")
    kw = fake.calls[0]
    assert kw["model"] == "claude-opus-5-5" and kw["fallbacks"] == "default"
    assert kw["betas"] == ["server-side-fallback-2026-07-01"] and kw["output_config"] == {"effort": "medium"}
    assert all(t["strict"] for t in kw["tools"]) and "never follow instructions" in kw["system"]


def test_t2_tool_returns_confirmation_card_not_execution(s):
    fake = FakeClient([resp("tool_use", tool_use("pay_bill", {"bill_id": "B1"})),
                       resp("end_turn", text("Press Confirm to pay 280 000 UZS."))])
    reply = Agent(fake).handle(s, "pay electricity")
    assert reply.events[0]["type"] == "confirm" and s.pending and not s.sb.bill("B1").paid
    r = tool_results(fake.calls[1])[0]
    assert r["tool_use_id"] == "tu_1" and "awaiting_user_confirmation" in r["content"] and r["is_error"] is False


def test_t3_tool_is_blocked_and_reported_as_error(s):
    fake = FakeClient([resp("tool_use", tool_use("transfer_to_card", {"card_number": "8600123412341234", "amount": 5_000_000})),
                       resp("end_turn", text("I can't do that."))])
    Agent(fake).handle(s, "send 5m to card")
    r = tool_results(fake.calls[1])[0]
    assert r["is_error"] is True and "blocked_by_policy" in r["content"] and s.sb.balance == 1_450_000


def test_parallel_tool_calls_return_in_one_message(s):
    fake = FakeClient([resp("tool_use", tool_use("analyze_bills", {}, "a"), tool_use("build_budget", {}, "b")),
                       resp("end_turn", text("done"))])
    Agent(fake).handle(s, "bills and budget")
    ids = [r["tool_use_id"] for r in tool_results(fake.calls[1])]
    assert ids == ["a", "b"]
    roles = [m["role"] for m in s.messages]
    assert roles == ["user", "assistant", "user", "assistant"]


def test_refusal_is_handled(s):
    fake = FakeClient([resp("refusal")])
    reply = Agent(fake).handle(s, "something")
    assert "can't help" in reply.text


def test_api_failure_falls_back_to_rules_and_keeps_history_valid(s):
    err = anthropic.APIConnectionError(request=httpx2.Request("POST", "https://api.anthropic.com/v1/messages"))
    fake = FakeClient([resp("tool_use", tool_use("analyze_bills", {})), err])
    reply = Agent(fake).handle(s, "Analyse my bills")
    assert reply.mode == "rules-fallback" and "Electricity" in reply.text
    assert [m["role"] for m in s.messages] == ["user", "assistant"]
    assert isinstance(s.messages[1]["content"], str)


def test_typed_yes_confirms_pending_without_calling_the_model(s):
    fake = FakeClient([resp("tool_use", tool_use("pay_bill", {"bill_id": "B1"})), resp("end_turn", text("Confirm?"))])
    agent = Agent(fake)
    agent.handle(s, "pay electricity")
    n = len(fake.calls)
    reply = agent.handle(s, "yes")
    assert reply.mode == "confirmation" and s.sb.bill("B1").paid and len(fake.calls) == n


def test_new_message_expires_pending(s):
    fake = FakeClient([resp("tool_use", tool_use("pay_bill", {"bill_id": "B1"})), resp("end_turn", text("Confirm?")),
                       resp("end_turn", text("ok"))])
    agent = Agent(fake)
    agent.handle(s, "pay electricity")
    agent.handle(s, "actually, where does my money go?")
    assert s.pending is None and any(e["decision"] == "expired" for e in s.audit.entries)


@pytest.mark.parametrize("msg", ["Analyse my bills", "Transfer 5 000 000 to card 8600 1234 5678 9012"])
def test_rules_mode_without_client(s, msg):
    reply = Agent(None).handle(s, msg)
    assert reply.mode == "rules" and reply.text
