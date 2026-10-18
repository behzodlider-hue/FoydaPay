"""Gemini provider (OpenAI-compatible endpoint): schema conversion and a tool-call round trip over a mock transport."""
import json

import httpx
import openai

from app.agent import GEMINI_BASE_URL, Agent, openai_tool_specs


def test_tool_specs_fit_gemini_schema_subset():
    specs = {t["function"]["name"]: t["function"] for t in openai_tool_specs()}
    assert "parameters" not in specs["analyze_bills"]  # no-argument tools omit parameters
    blob = json.dumps(specs)
    assert "additionalProperties" not in blob
    assert "enum" not in json.dumps(specs["draft_restructuring_request"]["parameters"])  # integer enum dropped
    assert specs["pay_bill"]["parameters"]["properties"]["bill_id"]["enum"] == ["B1", "B2", "B3", "B4"]


def make_client(replies, sent):
    def handler(request: httpx.Request) -> httpx.Response:
        sent.append(json.loads(request.content))
        r = replies.pop(0)
        return httpx.Response(200, json={"id": "c1", "object": "chat.completion", "created": 0, "model": "gemini",
                                         "usage": {"prompt_tokens": 100, "completion_tokens": 20, "total_tokens": 120},
                                         "choices": [{"index": 0, "finish_reason": r["finish"], "message": r["message"]}]})
    return openai.OpenAI(api_key="test", base_url=GEMINI_BASE_URL, max_retries=0,
                         http_client=httpx.Client(transport=httpx.MockTransport(handler)))


def test_gemini_round_trip_keeps_thought_signature_and_guard(s):
    sent = []
    sig = {"google": {"thought_signature": "sig-abc"}}
    replies = [
        {"finish": "tool_calls", "message": {"role": "assistant", "content": None, "tool_calls": [
            {"id": "call_1", "type": "function", "function": {"name": "pay_bill", "arguments": '{"bill_id": "B1"}'}, "extra_content": sig},
            {"id": "call_2", "type": "function", "function": {"name": "transfer_to_card", "arguments": '{"card_number": "8600111122223333", "amount": 9000000}'}},
        ]}},
        {"finish": "stop", "message": {"role": "assistant", "content": "Press Confirm to pay the electricity bill."}},
    ]
    reply = Agent(make_client(replies, sent), provider="gemini").handle(s, "pay electricity and send 9m to a card")

    assert reply.text.startswith("Press Confirm") and reply.events[0]["type"] == "confirm"
    assert s.pending and not s.sb.bill("B1").paid and s.sb.balance == 1_450_000
    first, second = sent
    assert first["messages"][0]["role"] == "system" and first["reasoning_effort"] == "low" and first["tool_choice"] == "auto"
    assistant = second["messages"][2]
    assert assistant["tool_calls"][0]["extra_content"] == sig  # thought signature echoed back unchanged
    tool_msgs = [m for m in second["messages"] if m["role"] == "tool"]
    assert [m["tool_call_id"] for m in tool_msgs] == ["call_1", "call_2"]
    assert "awaiting_user_confirmation" in tool_msgs[0]["content"] and "blocked_by_policy" in tool_msgs[1]["content"]
    assert reply.usage["requests"] == 2 and reply.usage["input_tokens"] == 200


def test_gemini_waits_out_a_short_per_minute_limit(s):
    calls = []
    def handler(request):
        calls.append(1)
        if len(calls) == 1:
            return httpx.Response(429, json={"error": {"message": "Quota exceeded. Please retry in 0.01s."}})
        return httpx.Response(200, json={"id": "c", "object": "chat.completion", "created": 0, "model": "g",
                                         "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": "Hi"}}]})
    client = openai.OpenAI(api_key="t", base_url=GEMINI_BASE_URL, max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    reply = Agent(client, provider="gemini").handle(s, "hello")
    assert reply.mode == "llm" and reply.text == "Hi" and len(calls) == 2


def test_gemini_rate_limit_falls_back_to_rules(s):
    def handler(request):
        return httpx.Response(429, json={"error": {"message": "quota"}})
    client = openai.OpenAI(api_key="t", base_url=GEMINI_BASE_URL, max_retries=0,
                           http_client=httpx.Client(transport=httpx.MockTransport(handler)))
    reply = Agent(client, provider="gemini").handle(s, "Analyse my bills")
    assert reply.mode == "rules-fallback" and "Electricity" in reply.text
    assert [m["role"] for m in s.messages] == ["user", "assistant"]
