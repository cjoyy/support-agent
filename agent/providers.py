from __future__ import annotations

import json
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

import httpx

from dotenv import load_dotenv
from google import genai


GEMINI_MODEL = "gemini-2.5-flash-lite"
GROQ_MODEL = "llama-3.3-70b-versatile"


@dataclass
class ToolCall:
    name: str
    args: dict[str, Any]
    id: str | None = None


@dataclass
class ProviderResponse:
    text: str = ""
    tool_calls: list[ToolCall] = field(default_factory=list)
    raw: Any = None
    input_tokens: int = 0
    output_tokens: int = 0


class LLMProvider(ABC):
    name: str

    @abstractmethod
    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        raise NotImplementedError


GEMINI_TYPE_MAP = {
    "object": genai.types.Type.OBJECT,
    "string": genai.types.Type.STRING,
    "number": genai.types.Type.NUMBER,
    "integer": genai.types.Type.INTEGER,
    "boolean": genai.types.Type.BOOLEAN,
    "array": genai.types.Type.ARRAY,
}


def _to_gemini_schema(schema: dict[str, Any]) -> genai.types.Schema:
    kwargs: dict[str, Any] = {"type": GEMINI_TYPE_MAP[schema["type"]]}
    for key in ("description", "enum", "required"):
        if value := schema.get(key):
            kwargs[key] = value

    if properties := schema.get("properties"):
        kwargs["properties"] = {
            name: _to_gemini_schema(property_schema)
            for name, property_schema in properties.items()
        }

    if items := schema.get("items"):
        kwargs["items"] = _to_gemini_schema(items)

    return genai.types.Schema(**kwargs)


def to_gemini_tool(schemas: list[dict[str, Any]]) -> genai.types.Tool:
    return genai.types.Tool(
        functionDeclarations=[
            genai.types.FunctionDeclaration(
                name=schema["name"],
                description=schema["description"],
                parameters=_to_gemini_schema(schema["input_schema"]),
            )
            for schema in schemas
        ]
    )


def to_openai_tools(schemas: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "type": "function",
            "function": {
                "name": schema["name"],
                "description": schema["description"],
                "parameters": schema["input_schema"],
            },
        }
        for schema in schemas
    ]


def _gemini_content(message: dict[str, Any]) -> genai.types.Content:
    role = "model" if message["role"] == "assistant" else "user"

    if message["role"] == "tool":
        return genai.types.Content(
            role="user",
            parts=[
                genai.types.Part(
                    functionResponse=genai.types.FunctionResponse(
                        id=message.get("tool_call_id"),
                        name=message["name"],
                        response={"result": message["content"]},
                    )
                )
            ],
        )

    if tool_calls := message.get("tool_calls"):
        return genai.types.Content(
            role="model",
            parts=[
                genai.types.Part(
                    functionCall=genai.types.FunctionCall(
                        id=tool_call.get("id"),
                        name=tool_call["name"],
                        args=tool_call["args"],
                    )
                )
                for tool_call in tool_calls
            ],
        )

    return genai.types.Content(role=role, parts=[genai.types.Part(text=message.get("content", ""))])


def _usage_counts(response: Any) -> tuple[int, int]:
    usage_metadata = getattr(response, "usage_metadata", None)
    if usage_metadata is None:
        return 0, 0

    input_tokens = getattr(usage_metadata, "prompt_token_count", None) or 0
    output_tokens = getattr(usage_metadata, "candidates_token_count", None) or 0
    return int(input_tokens), int(output_tokens)


class GeminiProvider(LLMProvider):
    name = "gemini"

    def __init__(self, api_key: str | None = None, model: str = GEMINI_MODEL, system_prompt: str | None = None) -> None:
        load_dotenv()
        resolved_key = api_key or os.getenv("GEMINI_API_KEY")
        if not resolved_key:
            raise RuntimeError("GEMINI_API_KEY is not set")

        self.client = genai.Client(api_key=resolved_key)
        self.model = model
        self.system_prompt = system_prompt

    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        response = self.client.models.generate_content(
            model=self.model,
            contents=[_gemini_content(message) for message in messages],
            config=genai.types.GenerateContentConfig(
                tools=[to_gemini_tool(tools)],
                systemInstruction=self.system_prompt,
            ),
        )

        parts = response.candidates[0].content.parts or []
        tool_calls = [
            ToolCall(
                id=getattr(part.function_call, "id", None),
                name=part.function_call.name,
                args=dict(part.function_call.args or {}),
            )
            for part in parts
            if part.function_call
        ]
        text = "".join(getattr(part, "text", "") for part in parts if getattr(part, "text", "")).strip()
        input_tokens, output_tokens = _usage_counts(response)
        return ProviderResponse(
            text=text,
            tool_calls=tool_calls,
            raw=response,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )


class _OpenAICompatProvider(LLMProvider):
    """Base for OpenAI-compatible providers (Groq, Cerebras, etc.)."""

    name: str = ""
    api_key_env: str = ""
    api_base: str = ""
    model: str = ""
    system_prompt: str | None = None
    _client: Any | None = None

    def _ensure_client(self) -> Any:
        if not self.api_key:
            raise RuntimeError(f"{self.api_key_env} is not set")
        if self._client is None:
            from openai import OpenAI

            self._client = OpenAI(api_key=self.api_key, base_url=self.api_base)
        return self._client

    def _messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        converted: list[dict[str, Any]] = []
        if self.system_prompt:
            converted.append({"role": "system", "content": self.system_prompt})

        for message in messages:
            if message["role"] == "assistant" and message.get("tool_calls"):
                converted.append(
                    {
                        "role": "assistant",
                        "content": message.get("content") or "",
                        "tool_calls": [
                            {
                                "id": tool_call.get("id") or f"call_{index}",
                                "type": "function",
                                "function": {
                                    "name": tool_call["name"],
                                    "arguments": json.dumps(tool_call["args"], ensure_ascii=False),
                                },
                            }
                            for index, tool_call in enumerate(message["tool_calls"])
                        ],
                    }
                )
            elif message["role"] == "tool":
                converted.append(
                    {
                        "role": "tool",
                        "tool_call_id": message.get("tool_call_id") or "call_0",
                        "content": json.dumps(message["content"], ensure_ascii=False, default=str),
                    }
                )
            else:
                converted.append({"role": message["role"], "content": message.get("content", "")})

        return converted

    def generate(self, messages: list[dict[str, Any]], tools: list[dict[str, Any]]) -> ProviderResponse:
        response = self._ensure_client().chat.completions.create(
            model=self.model,
            messages=self._messages(messages),
            tools=to_openai_tools(tools),
            tool_choice="auto",
        )
        choice = response.choices[0].message
        tool_calls = [
            ToolCall(
                id=tool_call.id,
                name=tool_call.function.name,
                args=json.loads(tool_call.function.arguments or "{}"),
            )
            for tool_call in (choice.tool_calls or [])
        ]
        usage = getattr(response, "usage", None)
        return ProviderResponse(
            text=choice.content or "",
            tool_calls=tool_calls,
            raw=response,
            input_tokens=int(getattr(usage, "prompt_tokens", 0) or 0),
            output_tokens=int(getattr(usage, "completion_tokens", 0) or 0),
        )


class GroqProvider(_OpenAICompatProvider):
    name = "groq"
    api_key_env = "GROQ_API_KEY"
    api_base = "https://api.groq.com/openai/v1"

    def __init__(self, api_key: str | None = None, model: str = GROQ_MODEL, system_prompt: str | None = None) -> None:
        load_dotenv()
        self.api_key = api_key or os.getenv("GROQ_API_KEY")
        self.model = model
        self.system_prompt = system_prompt



