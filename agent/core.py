from __future__ import annotations

import json
import os
import re
import time
from typing import Any

from google import genai
from google.genai.errors import APIError
from dotenv import load_dotenv

from tools.handlers import TOOL_MAP
from tools.schemas import schemas


MODEL_NAME = "gemini-2.5-flash-lite"
MAX_RATE_LIMIT_RETRIES = 2
DEFAULT_RATE_LIMIT_RETRY_SECONDS = 35

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


TYPE_MAP = {
    "object": genai.types.Type.OBJECT,
    "string": genai.types.Type.STRING,
    "number": genai.types.Type.NUMBER,
    "integer": genai.types.Type.INTEGER,
    "boolean": genai.types.Type.BOOLEAN,
    "array": genai.types.Type.ARRAY,
}


def _to_gemini_schema(schema: dict[str, Any]) -> genai.types.Schema:
    schema_type = TYPE_MAP[schema["type"]]
    kwargs: dict[str, Any] = {"type": schema_type}

    if description := schema.get("description"):
        kwargs["description"] = description

    if enum_values := schema.get("enum"):
        kwargs["enum"] = enum_values

    if properties := schema.get("properties"):
        kwargs["properties"] = {
            name: _to_gemini_schema(property_schema)
            for name, property_schema in properties.items()
        }

    if required := schema.get("required"):
        kwargs["required"] = required

    if items := schema.get("items"):
        kwargs["items"] = _to_gemini_schema(items)

    return genai.types.Schema(**kwargs)


def _to_function_declaration(schema: dict[str, Any]) -> genai.types.FunctionDeclaration:
    return genai.types.FunctionDeclaration(
        name=schema["name"],
        description=schema["description"],
        parameters=_to_gemini_schema(schema["input_schema"]),
    )


tool_schema = genai.types.Tool(
    functionDeclarations=[_to_function_declaration(schema) for schema in schemas]
)


def _retry_delay_seconds(exc: Exception) -> int:
    match = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", str(exc))
    if match:
        return int(match.group(1)) + 1

    match = re.search(r"Please retry in ([\d.]+)s", str(exc))
    if match:
        return int(float(match.group(1))) + 1

    return DEFAULT_RATE_LIMIT_RETRY_SECONDS


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", None) or getattr(exc, "code", None)
    if status_code == 429:
        return True

    message = str(exc).lower()
    return "quota" in message or "rate limit" in message or "resourceexhausted" in message


def _response_text(parts: Any) -> str:
    return "".join(getattr(part, "text", "") for part in parts if getattr(part, "text", "")).strip()


def _kb_has_relevant_matches(tool_result: Any) -> bool:
    if not isinstance(tool_result, dict):
        return False
    matches = tool_result.get("matches")
    return isinstance(matches, list) and len(matches) > 0


def _user_content(text: str) -> genai.types.Content:
    return genai.types.Content(role="user", parts=[genai.types.Part(text=text)])


def _function_response_content(tool_name: str, tool_result: Any) -> genai.types.Content:
    return genai.types.Content(
        role="user",
        parts=[
            genai.types.Part(
                functionResponse=genai.types.FunctionResponse(
                    name=tool_name,
                    response={"result": tool_result},
                )
            )
        ],
    )


class SupportAgent:
    def __init__(self, api_key: str | None = None, model_name: str = MODEL_NAME) -> None:
        load_dotenv()
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=resolved_key)
        self.model_name = model_name
        self.config = genai.types.GenerateContentConfig(
            tools=[tool_schema],
            systemInstruction=SYSTEM_PROMPT,
        )

    def chat(self, user_message: str, conversation_history: list[Any]) -> str:
        contents = list(conversation_history)
        next_message = _user_content(user_message)
        rate_limit_retries = 0

        while True:
            request_contents = contents + [next_message]
            try:
                response = self.client.models.generate_content(
                    model=self.model_name,
                    contents=request_contents,
                    config=self.config,
                )
            except APIError as exc:
                if not _is_rate_limit_error(exc) or rate_limit_retries >= MAX_RATE_LIMIT_RETRIES:
                    raise

                rate_limit_retries += 1
                delay_seconds = _retry_delay_seconds(exc)
                print(
                    "RATE_LIMIT_RETRY "
                    f"attempt={rate_limit_retries}/{MAX_RATE_LIMIT_RETRIES} "
                    f"sleep_seconds={delay_seconds}"
                )
                time.sleep(delay_seconds)
                continue

            rate_limit_retries = 0
            response_content = response.candidates[0].content
            contents = request_contents + [response_content]
            parts = response_content.parts or []

            function_call = next(
                (part.function_call for part in parts if part.function_call),
                None,
            )
            if function_call is None:
                text = _response_text(parts)
                conversation_history.clear()
                conversation_history.extend(contents)
                return text or "Maaf, saya tidak bisa memberikan jawaban yang aman saat ini."

            tool_name = function_call.name
            tool_args = dict(function_call.args)

            print(f"FUNCTION_CALL name={tool_name} args={json.dumps(tool_args, ensure_ascii=False)}")

            handler = TOOL_MAP.get(tool_name)
            if handler is None:
                tool_result: Any = {"error": f"Unknown tool: {tool_name}"}
            else:
                try:
                    tool_result = handler(**tool_args)
                except Exception as exc:
                    tool_result = {"error": str(exc)}

            if tool_name == "search_knowledge_base" and not _kb_has_relevant_matches(tool_result):
                escalate_args = {"reason": "no relevant info found"}
                print(
                    "FUNCTION_CALL "
                    f"name=escalate_to_human args={json.dumps(escalate_args, ensure_ascii=False)}"
                )
                TOOL_MAP["escalate_to_human"](**escalate_args)
                conversation_history.clear()
                conversation_history.extend(contents)
                return (
                    "Maaf, saya belum menemukan informasi yang relevan di knowledge base. "
                    "Saya akan eskalasikan percakapan ini ke agent manusia."
                )

            if tool_name == "escalate_to_human":
                conversation_history.clear()
                conversation_history.extend(contents)
                return "Saya akan eskalasikan percakapan ini ke agent manusia agar bisa ditangani lebih lanjut."

            next_message = _function_response_content(tool_name, tool_result)
