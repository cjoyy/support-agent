from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from typing import Any

from dotenv import load_dotenv

from agent.providers import GeminiProvider, GroqProvider, LLMProvider, ProviderResponse, ToolCall
from agent.resilience import CircuitBreaker, CircuitOpenError
from tools.handlers import (
    TOOL_MAP,
    append_jsonl,
    print_and_log_agent_event,
    reset_request_id,
    set_request_id,
    usage_log_path,
)
from tools.schemas import schemas


MODEL_NAME = "gemini-2.5-flash-lite"
MAX_RATE_LIMIT_RETRIES = 2
INPUT_COST_PER_1M_TOKEN = 0.10
OUTPUT_COST_PER_1M_TOKEN = 0.40

SYSTEM_PROMPT = (
    "You are a customer support agent. "
    "You may only answer customer support questions related to orders, refunds, shipping, accounts, billing, "
    "and service policies. If the user asks about anything outside customer support, politely refuse and redirect "
    "them back to support topics you can help with. "
    "For general support questions, call search_knowledge_base first before answering. "
    "If search_knowledge_base returns empty or irrelevant matches, do not invent an answer; immediately call "
    "escalate_to_human with reason 'no relevant info found'. "
    "For specific order questions with an order ID, call check_order_status. "
    "If the user explicitly asks for a human, or if you are not confident after tools, call escalate_to_human. "
    "If the user seems frustrated, uses harsh language, says they are not satisfied, or complains after two "
    "interactions, proactively offer to escalate_to_human. "
    "Use create_ticket when the issue needs formal follow-up tracking. "
    "Never invent policy, order, or ticket details."
)


def _kb_has_relevant_matches(tool_result: Any) -> bool:
    if not isinstance(tool_result, dict):
        return False
    matches = tool_result.get("matches")
    return isinstance(matches, list) and len(matches) > 0


def _estimated_cost_usd(input_tokens: int, output_tokens: int) -> float:
    return (
        (input_tokens / 1_000_000) * INPUT_COST_PER_1M_TOKEN
        + (output_tokens / 1_000_000) * OUTPUT_COST_PER_1M_TOKEN
    )


def _assistant_tool_message(tool_calls: list[ToolCall]) -> dict[str, Any]:
    return {
        "role": "assistant",
        "content": "",
        "tool_calls": [
            {
                "id": tool_call.id or f"call_{index}",
                "name": tool_call.name,
                "args": tool_call.args,
            }
            for index, tool_call in enumerate(tool_calls)
        ],
    }


def _tool_result_message(tool_call: ToolCall, tool_result: Any) -> dict[str, Any]:
    return {
        "role": "tool",
        "tool_call_id": tool_call.id or "call_0",
        "name": tool_call.name,
        "content": tool_result,
    }


class SupportAgent:
    def __init__(
        self,
        api_key: str | None = None,
        model_name: str = MODEL_NAME,
        primary_provider: LLMProvider | None = None,
        fallback_provider: LLMProvider | None = None,
        circuit_breaker: CircuitBreaker | None = None,
    ) -> None:
        load_dotenv()
        self.primary_provider = primary_provider or GeminiProvider(
            api_key=api_key,
            model=model_name,
            system_prompt=SYSTEM_PROMPT,
        )
        self.fallback_provider = fallback_provider or GroqProvider(system_prompt=SYSTEM_PROMPT)
        self.circuit_breaker = circuit_breaker or CircuitBreaker()

    def _generate(self, messages: list[dict[str, Any]], request_id: str | None) -> ProviderResponse:
        try:
            return self.circuit_breaker.call(self.primary_provider.generate, messages, schemas)
        except CircuitOpenError as exc:
            reason = str(exc)
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"

        print_and_log_agent_event(
            {
                "event": "fallback_used",
                "request_id": request_id,
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "primary_provider": self.primary_provider.name,
                "fallback_provider": self.fallback_provider.name,
                "reason": reason,
                "circuit_state": self.circuit_breaker.state,
            }
        )
        return self.fallback_provider.generate(messages, schemas)

    def chat(self, user_message: str, conversation_history: list[Any], request_id: str | None = None) -> str:
        request_token = set_request_id(request_id)
        total_started_at = time.perf_counter()
        llm_time_ms = 0.0
        retrieval_time_ms = 0.0
        input_tokens_total = 0
        output_tokens_total = 0
        messages = list(conversation_history)
        messages.append({"role": "user", "content": user_message})

        try:
            while True:
                llm_started_at = time.perf_counter()
                response = self._generate(messages, request_id)
                llm_time_ms += (time.perf_counter() - llm_started_at) * 1000
                input_tokens_total += response.input_tokens
                output_tokens_total += response.output_tokens

                if not response.tool_calls:
                    messages.append({"role": "assistant", "content": response.text})
                    conversation_history.clear()
                    conversation_history.extend(messages)
                    return response.text or "Maaf, saya tidak bisa memberikan jawaban yang aman saat ini."

                messages.append(_assistant_tool_message(response.tool_calls))

                for tool_call in response.tool_calls:
                    print(
                        "FUNCTION_CALL "
                        f"request_id={request_id} "
                        f"name={tool_call.name} args={json.dumps(tool_call.args, ensure_ascii=False)}"
                    )

                    handler = TOOL_MAP.get(tool_call.name)
                    if handler is None:
                        tool_result: Any = {"error": f"Unknown tool: {tool_call.name}"}
                    else:
                        tool_started_at = time.perf_counter()
                        try:
                            tool_result = handler(**tool_call.args)
                        except Exception as exc:
                            tool_result = {"error": str(exc)}
                        finally:
                            if tool_call.name == "search_knowledge_base":
                                retrieval_time_ms += (time.perf_counter() - tool_started_at) * 1000

                    if tool_call.name == "search_knowledge_base" and not _kb_has_relevant_matches(tool_result):
                        escalate_args = {"reason": "no relevant info found"}
                        print(
                            "FUNCTION_CALL "
                            f"request_id={request_id} "
                            f"name=escalate_to_human args={json.dumps(escalate_args, ensure_ascii=False)}"
                        )
                        TOOL_MAP["escalate_to_human"](**escalate_args)
                        conversation_history.clear()
                        conversation_history.extend(messages)
                        return (
                            "Maaf, saya belum menemukan informasi yang relevan di knowledge base. "
                            "Saya akan eskalasikan percakapan ini ke agent manusia."
                        )

                    if tool_call.name == "escalate_to_human":
                        conversation_history.clear()
                        conversation_history.extend(messages)
                        return "Saya akan eskalasikan percakapan ini ke agent manusia agar bisa ditangani lebih lanjut."

                    messages.append(_tool_result_message(tool_call, tool_result))
        finally:
            total_time_ms = (time.perf_counter() - total_started_at) * 1000
            timestamp = datetime.now(timezone.utc).isoformat()
            append_jsonl(
                usage_log_path(),
                {
                    "request_id": request_id,
                    "timestamp": timestamp,
                    "input_tokens": input_tokens_total,
                    "output_tokens": output_tokens_total,
                    "estimated_cost_usd": round(
                        _estimated_cost_usd(input_tokens_total, output_tokens_total),
                        10,
                    ),
                },
            )
            print_and_log_agent_event(
                {
                    "event": "latency_breakdown",
                    "request_id": request_id,
                    "timestamp": timestamp,
                    "retrieval_time_ms": round(retrieval_time_ms, 2),
                    "llm_time_ms": round(llm_time_ms, 2),
                    "total_time_ms": round(total_time_ms, 2),
                }
            )
            reset_request_id(request_token)
