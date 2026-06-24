from __future__ import annotations

from unittest.mock import Mock

import pytest

from agent.core import SupportAgent
from agent.providers import ProviderResponse, ToolCall
from agent.resilience import CircuitBreaker


@pytest.fixture
def isolated_agent_logs(monkeypatch, tmp_path):
    import agent.core as core

    monkeypatch.setattr(core, "usage_log_path", lambda: tmp_path / "usage_log.jsonl")
    monkeypatch.setattr(core, "print_and_log_agent_event", Mock())
    return core


def provider(name: str, side_effect=None, return_value=None) -> Mock:
    mocked = Mock()
    mocked.name = name
    mocked.generate = Mock(side_effect=side_effect, return_value=return_value)
    return mocked


def test_agent_calls_search_knowledge_base_tool(isolated_agent_logs, monkeypatch):
    search_tool = Mock(
        return_value={
            "query": "bagaimana cara refund?",
            "matches": [{"text": "Refunds take 5 to 10 business days.", "similarity": 0.9}],
        }
    )
    monkeypatch.setitem(isolated_agent_logs.TOOL_MAP, "search_knowledge_base", search_tool)

    primary = provider(
        "gemini",
        side_effect=[
            ProviderResponse(
                tool_calls=[
                    ToolCall(
                        name="search_knowledge_base",
                        args={"query": "bagaimana cara refund?"},
                    )
                ],
                input_tokens=12,
                output_tokens=3,
            ),
            ProviderResponse(
                text="Refunds usually take 5 to 10 business days.",
                input_tokens=10,
                output_tokens=5,
            ),
        ],
    )
    fallback = provider("groq", return_value=ProviderResponse(text="fallback"))

    agent = SupportAgent(primary_provider=primary, fallback_provider=fallback)
    history: list[object] = []
    response, tools_used = agent.chat("bagaimana cara refund?", history, request_id="test-request")

    assert response == "Refunds usually take 5 to 10 business days."
    assert tools_used == ["search_knowledge_base"]
    assert search_tool.call_args.kwargs == {"query": "bagaimana cara refund?"}
    assert primary.generate.call_count == 2
    fallback.generate.assert_not_called()


def test_agent_returns_direct_text_without_tool_loop(isolated_agent_logs):
    primary = provider(
        "gemini",
        return_value=ProviderResponse(text="Maaf, saya hanya bisa membantu topik customer support."),
    )
    fallback = provider("groq", return_value=ProviderResponse(text="fallback"))

    agent = SupportAgent(primary_provider=primary, fallback_provider=fallback)
    history: list[object] = []
    response, tools_used = agent.chat("ceritakan resep nasi goreng", history, request_id="test-request")

    assert response == "Maaf, saya hanya bisa membantu topik customer support."
    assert tools_used == []
    assert primary.generate.call_count == 1
    fallback.generate.assert_not_called()


def test_agent_opens_circuit_and_uses_groq_fallback(isolated_agent_logs):
    primary = provider("gemini", side_effect=RuntimeError("gemini down"))
    fallback = provider("groq", return_value=ProviderResponse(text="fallback response"))
    circuit_breaker = CircuitBreaker(failure_threshold=3, recovery_timeout=60)

    agent = SupportAgent(
        primary_provider=primary,
        fallback_provider=fallback,
        circuit_breaker=circuit_breaker,
    )

    for index in range(3):
        assert agent.chat(f"message {index}", [], request_id=f"fallback-{index}") == (
            "fallback response",
            [],
        )

    assert circuit_breaker.state == CircuitBreaker.OPEN
    assert primary.generate.call_count == 3

    assert agent.chat("message 4", [], request_id="fallback-open") == ("fallback response", [])
    assert primary.generate.call_count == 3
    assert fallback.generate.call_count == 4

    fallback_events = [
        call.args[0]
        for call in isolated_agent_logs.print_and_log_agent_event.call_args_list
        if call.args and call.args[0].get("event") == "fallback_used"
    ]
    assert fallback_events
    assert fallback_events[-1]["fallback_provider"] == "groq"
