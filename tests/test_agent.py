from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from agent import core


def fake_text_response(text: str) -> SimpleNamespace:
    part = SimpleNamespace(text=text, function_call=None)
    content = SimpleNamespace(parts=[part])
    usage = SimpleNamespace(prompt_token_count=10, candidates_token_count=5)
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)], usage_metadata=usage)


def fake_function_call_response(name: str, args: dict[str, object]) -> SimpleNamespace:
    function_call = SimpleNamespace(name=name, args=args)
    part = SimpleNamespace(text=None, function_call=function_call)
    content = SimpleNamespace(parts=[part])
    usage = SimpleNamespace(prompt_token_count=12, candidates_token_count=3)
    return SimpleNamespace(candidates=[SimpleNamespace(content=content)], usage_metadata=usage)


@pytest.fixture
def mock_agent_client(monkeypatch, tmp_path):
    fake_client = SimpleNamespace(models=SimpleNamespace(generate_content=Mock()))
    monkeypatch.setattr(core.genai, "Client", Mock(return_value=fake_client))
    monkeypatch.setattr(core, "usage_log_path", lambda: tmp_path / "usage_log.jsonl")
    monkeypatch.setattr(core, "print_and_log_agent_event", Mock())
    return fake_client


def test_agent_calls_search_knowledge_base_tool(mock_agent_client, monkeypatch):
    search_tool = Mock(
        return_value={
            "query": "bagaimana cara refund?",
            "matches": [{"text": "Refunds take 5 to 10 business days.", "similarity": 0.9}],
        }
    )
    monkeypatch.setitem(core.TOOL_MAP, "search_knowledge_base", search_tool)

    mock_agent_client.models.generate_content.side_effect = [
        fake_function_call_response(
            "search_knowledge_base",
            {"query": "bagaimana cara refund?"},
        ),
        fake_text_response("Refunds usually take 5 to 10 business days."),
    ]

    agent = core.SupportAgent(api_key="test-key")
    history: list[object] = []
    response = agent.chat("bagaimana cara refund?", history, request_id="test-request")

    assert response == "Refunds usually take 5 to 10 business days."
    assert search_tool.call_args.kwargs == {"query": "bagaimana cara refund?"}
    assert mock_agent_client.models.generate_content.call_count == 2


def test_agent_returns_direct_text_without_tool_loop(mock_agent_client):
    mock_agent_client.models.generate_content.return_value = fake_text_response(
        "Maaf, saya hanya bisa membantu topik customer support."
    )

    agent = core.SupportAgent(api_key="test-key")
    history: list[object] = []
    response = agent.chat("ceritakan resep nasi goreng", history, request_id="test-request")

    assert response == "Maaf, saya hanya bisa membantu topik customer support."
    assert mock_agent_client.models.generate_content.call_count == 1
