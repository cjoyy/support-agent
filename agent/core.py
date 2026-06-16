from __future__ import annotations

import json
import os
from typing import Any

from anthropic import Anthropic
from dotenv import load_dotenv

from tools.handlers import TOOL_MAP
from tools.schemas import schemas


SYSTEM_PROMPT = (
    "You are a customer support agent. "
    "For general support questions, call search_knowledge_base first before answering. "
    "For specific order questions with an order ID, call check_order_status. "
    "If the user explicitly asks for a human, or if you are not confident after tools, call escalate_to_human. "
    "Use create_ticket when the issue needs formal follow-up tracking. "
    "Never invent policy, order, or ticket details."
)


def _block_to_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump()
    if hasattr(block, "dict"):
        return block.dict()
    return dict(block)


def _block_type(block: Any) -> str | None:
    if isinstance(block, dict):
        return block.get("type")
    return getattr(block, "type", None)


def _block_text(block: Any) -> str:
    if isinstance(block, dict):
        return block.get("text", "")
    return getattr(block, "text", "")


def _tool_use_fields(block: Any) -> tuple[str, dict[str, Any], str]:
    if isinstance(block, dict):
        name = block.get("name", "")
        payload = block.get("input", {}) or {}
        tool_use_id = block.get("id") or block.get("tool_use_id") or ""
        return name, payload, tool_use_id

    name = getattr(block, "name", "")
    payload = getattr(block, "input", {}) or {}
    tool_use_id = getattr(block, "id", None) or getattr(block, "tool_use_id", None) or ""
    return name, payload, tool_use_id


class SupportAgent:
    def __init__(self, api_key: str | None = None) -> None:
        load_dotenv()
        resolved_key = api_key or os.getenv("ANTHROPIC_API_KEY")
        if not resolved_key:
            raise RuntimeError("ANTHROPIC_API_KEY is not set")
        self.client = Anthropic(api_key=resolved_key)

    def _extract_text(self, content: list[Any]) -> str:
        return "".join(_block_text(block) for block in content if _block_type(block) == "text").strip()

    def chat(self, user_message: str, conversation_history: list[dict[str, Any]]) -> str:
        conversation_history.append({"role": "user", "content": user_message})

        while True:
            response = self.client.messages.create(
                model="claude-sonnet-4-6",
                tools=schemas,
                messages=conversation_history,
                system=SYSTEM_PROMPT,
            )

            response_content = [_block_to_dict(block) for block in response.content]
            conversation_history.append({"role": "assistant", "content": response_content})

            if response.stop_reason == "tool_use":
                tool_result_blocks: list[dict[str, Any]] = []
                reason_parts: list[str] = []

                for block in response.content:
                    block_type = _block_type(block)
                    if block_type == "text":
                        reason_parts.append(_block_text(block))
                        continue

                    if block_type != "tool_use":
                        continue

                    tool_name, tool_input, tool_use_id = _tool_use_fields(block)
                    reason = " ".join(part.strip() for part in reason_parts if part.strip()).strip()
                    reason_parts = []

                    print(f"TOOL_USE name={tool_name} input={json.dumps(tool_input, ensure_ascii=False)}")
                    if reason:
                        print(f"TOOL_USE reason={reason}")

                    handler = TOOL_MAP.get(tool_name)
                    if handler is None:
                        tool_result = {"error": f"Unknown tool: {tool_name}"}
                    else:
                        try:
                            tool_result = handler(**tool_input)
                        except Exception as exc:
                            tool_result = {"error": str(exc)}

                    print(f"TOOL_RESULT name={tool_name} result={json.dumps(tool_result, ensure_ascii=False)}")
                    tool_result_blocks.append(
                        {
                            "type": "tool_result",
                            "tool_use_id": tool_use_id,
                            "content": json.dumps(tool_result, ensure_ascii=False),
                        }
                    )

                conversation_history.append({"role": "user", "content": tool_result_blocks})
                continue

            return self._extract_text(response_content)
