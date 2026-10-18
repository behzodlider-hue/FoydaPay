"""Offline check that the real Anthropic SDK accepts our request and parses a tool-use round trip (mock transport, no API spend)."""
import json

import anthropic
import httpx2

from app.agent import Agent


def test_real_sdk_round_trip_with_mock_transport(s):
    sent = []
    replies = [
        {"content": [{"type": "tool_use", "id": "toolu_1", "name": "pay_bill", "input": {"bill_id": "B1"}}], "stop_reason": "tool_use"},
        {"content": [{"type": "text", "text": "Press Confirm to pay 280 000 UZS."}], "stop_reason": "end_turn"},
    ]

    def handler(request: httpx2.Request) -> httpx2.Response:
        sent.append((dict(request.headers), json.loads(request.content)))
        r = replies.pop(0)
        return httpx2.Response(200, json={"id": "msg_1", "type": "message", "role": "assistant", "model": "claude-opus-5-5",
                                          "stop_sequence": None, "usage": {"input_tokens": 10, "output_tokens": 5}, **r})

    client = anthropic.Anthropic(api_key="test", http_client=httpx2.Client(transport=httpx2.MockTransport(handler)), max_retries=0)
    reply = Agent(client).handle(s, "Pay the electricity bill")

    assert reply.text.startswith("Press Confirm") and reply.events[0]["type"] == "confirm" and s.pending
    headers, body = sent[0]
    assert "server-side-fallback-2026-07-01" in headers["anthropic-beta"]
    assert body["model"] == "claude-opus-5-5" and body["fallbacks"] == "default"
    assert body["output_config"] == {"effort": "medium"} and body["cache_control"] == {"type": "ephemeral"}
    assert body["tools"][0]["strict"] is True
    _, second = sent[1]
    tool_result = second["messages"][-1]["content"][0]
    assert tool_result["type"] == "tool_result" and tool_result["tool_use_id"] == "toolu_1"
    assert second["messages"][1]["content"][0]["type"] == "tool_use"  # assistant content echoed back unchanged
