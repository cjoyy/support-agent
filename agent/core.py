from __future__ import annotations

import json
import os
import re
import time
from typing import Any

import google.generativeai as genai
from google.api_core.exceptions import ResourceExhausted
from dotenv import load_dotenv

from tools.handlers import TOOL_MAP
from tools.schemas import schemas


MODEL_NAME = "gemini-2.5-flash-lite"
MAX_RATE_LIMIT_RETRIES = 2
DEFAULT_RATE_LIMIT_RETRY_SECONDS = 35

SYSTEM_PROMPT = (
    "You are a customer support agent. "
    "For general support questions, call search_knowledge_base first before answering. "
    "For specific order questions with an order ID, call check_order_status. "
    "If the user explicitly asks for a human, or if you are not confident after tools, call escalate_to_human. "
    "Use create_ticket when the issue needs formal follow-up tracking. "
    "Never invent policy, order, or ticket details."
)


TYPE_MAP = {
    "object": genai.protos.Type.OBJECT,
    "string": genai.protos.Type.STRING,
    "number": genai.protos.Type.NUMBER,
    "integer": genai.protos.Type.INTEGER,
    "boolean": genai.protos.Type.BOOLEAN,
    "array": genai.protos.Type.ARRAY,
}


def _to_gemini_schema(schema: dict[str, Any]) -> genai.protos.Schema:
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

    return genai.protos.Schema(**kwargs)


def _to_function_declaration(schema: dict[str, Any]) -> genai.protos.FunctionDeclaration:
    return genai.protos.FunctionDeclaration(
        name=schema["name"],
        description=schema["description"],
        parameters=_to_gemini_schema(schema["input_schema"]),
    )


tool_schema = genai.protos.Tool(
    function_declarations=[_to_function_declaration(schema) for schema in schemas]
)


def _retry_delay_seconds(exc: ResourceExhausted) -> int:
    match = re.search(r"retry_delay\s*{\s*seconds:\s*(\d+)", str(exc))
    if match:
        return int(match.group(1)) + 1

    match = re.search(r"Please retry in ([\d.]+)s", str(exc))
    if match:
        return int(float(match.group(1))) + 1

    return DEFAULT_RATE_LIMIT_RETRY_SECONDS


class SupportAgent:
    def __init__(self, api_key: str | None = None, model_name: str = MODEL_NAME) -> None:
        load_dotenv()
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        genai.configure(api_key=resolved_key)
        self.model = genai.GenerativeModel(
            model_name,
            tools=[tool_schema],
            system_instruction=SYSTEM_PROMPT,
        )

    def chat(self, user_message: str, conversation_history: list[dict[str, Any]]) -> str:
        chat = self.model.start_chat(history=conversation_history)
        next_message: str | genai.protos.Part = user_message
        rate_limit_retries = 0

        while True:
            try:
                response = chat.send_message(next_message)
            except ResourceExhausted as exc:
                if rate_limit_retries >= MAX_RATE_LIMIT_RETRIES:
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
            parts = response.candidates[0].content.parts

            function_call = next(
                (part.function_call for part in parts if part.function_call),
                None,
            )
            if function_call is None:
                return response.text

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

            next_message = genai.protos.Part(
                function_response=genai.protos.FunctionResponse(
                    name=tool_name,
                    response={"result": tool_result},
                )
            )
