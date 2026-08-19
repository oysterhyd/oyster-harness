import json
from collections.abc import Sequence
from dataclasses import dataclass, field
from typing import cast

import httpx

from oyster_harness.llm.base import (
    ChatMessage,
    ModelResponse,
    TextCallback,
    ToolCall,
    ToolSchema,
)

DEFAULT_CHAT_ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_MODEL = "hy3"
CHAT_COMPLETION_MODELS = (
    "hy3",
    "hy3-preview",
    "grok-4.5",
    "glm-5.2",
    "glm-5.1",
    "kimi-k3",
    "kimi-k2.7-code",
    "kimi-k2.6",
    "deepseek-v4-pro",
    "deepseek-v4-flash",
    "mimo-v2.5-pro",
    "mimo-v2.5",
)


class OpenCodeAPIError(RuntimeError):
    """Raised when OpenCode Go rejects or cannot complete a request."""


class OpenCodeProvider:
    """Streaming OpenAI-compatible client for OpenCode Go."""

    def __init__(
        self,
        api_key: str,
        *,
        client: httpx.AsyncClient | None = None,
        timeout_seconds: float = 60.0,
    ) -> None:
        self._api_key = api_key
        self._client = client
        self._timeout = httpx.Timeout(timeout_seconds, connect=10.0)

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSchema] = (),
        model: str = DEFAULT_MODEL,
        reasoning_effort: str = "medium",
        on_text: TextCallback | None = None,
    ) -> ModelResponse:
        request: dict[str, object] = {
            "model": model,
            "messages": [_serialize_message(message) for message in messages],
            "reasoning_effort": reasoning_effort,
            "stream": True,
        }
        if tools:
            request["tools"] = [_serialize_tool(tool) for tool in tools]
            request["tool_choice"] = "auto"
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        if self._client is not None:
            try:
                return await self._complete_with_client(self._client, headers, request, on_text)
            except httpx.HTTPError as exc:
                raise OpenCodeAPIError(
                    f"OpenCode Go request failed: {type(exc).__name__}."
                ) from exc

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                return await self._complete_with_client(client, headers, request, on_text)
        except httpx.HTTPError as exc:
            raise OpenCodeAPIError(f"OpenCode Go request failed: {type(exc).__name__}.") from exc

    async def _complete_with_client(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        request: dict[str, object],
        on_text: TextCallback | None,
    ) -> ModelResponse:
        text_chunks: list[str] = []
        tool_calls: dict[int, _ToolCallBuilder] = {}
        finish_reason: str | None = None

        async with client.stream(
            "POST",
            DEFAULT_CHAT_ENDPOINT,
            headers=headers,
            json=request,
        ) as response:
            if response.is_error:
                detail = _extract_error(await response.aread())
                raise OpenCodeAPIError(
                    f"OpenCode Go returned HTTP {response.status_code}: {detail}"
                )

            async for line in response.aiter_lines():
                if not line.startswith("data:"):
                    continue

                data = line.removeprefix("data:").strip()
                if data == "[DONE]":
                    break

                event = _extract_event(data)
                if event.text:
                    text_chunks.append(event.text)
                    if on_text is not None:
                        on_text(event.text)
                finish_reason = event.finish_reason or finish_reason
                for tool_delta in event.tool_calls:
                    builder = tool_calls.setdefault(tool_delta.index, _ToolCallBuilder())
                    builder.add(tool_delta)

        completed_calls = tuple(
            builder.build(index) for index, builder in sorted(tool_calls.items())
        )
        return ModelResponse("".join(text_chunks), completed_calls, finish_reason)


@dataclass(frozen=True, slots=True)
class _ToolCallDelta:
    index: int
    id: str = ""
    name: str = ""
    arguments: str = ""


@dataclass(frozen=True, slots=True)
class _StreamEvent:
    text: str = ""
    tool_calls: tuple[_ToolCallDelta, ...] = ()
    finish_reason: str | None = None


@dataclass(slots=True)
class _ToolCallBuilder:
    id: str = ""
    name_parts: list[str] = field(default_factory=lambda: list[str]())
    argument_parts: list[str] = field(default_factory=lambda: list[str]())

    def add(self, delta: _ToolCallDelta) -> None:
        self.id = delta.id or self.id
        if delta.name:
            self.name_parts.append(delta.name)
        if delta.arguments:
            self.argument_parts.append(delta.arguments)

    def build(self, index: int) -> ToolCall:
        return ToolCall(
            id=self.id or f"call_{index}",
            name="".join(self.name_parts),
            arguments="".join(self.argument_parts),
        )


def _extract_event(data: str) -> _StreamEvent:
    try:
        payload = _as_object(json.loads(data))
    except json.JSONDecodeError as exc:
        raise OpenCodeAPIError("OpenCode Go returned an invalid stream event.") from exc

    if payload is None:
        return _StreamEvent()

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return _StreamEvent()

    choice = _as_object(cast(object, choices[0]))
    delta = _as_object(choice.get("delta")) if choice is not None else None
    content = delta.get("content") if delta is not None else None
    finish_reason = choice.get("finish_reason") if choice is not None else None
    return _StreamEvent(
        text=content if isinstance(content, str) else "",
        tool_calls=_extract_tool_deltas(delta),
        finish_reason=finish_reason if isinstance(finish_reason, str) else None,
    )


def _extract_tool_deltas(delta: dict[str, object] | None) -> tuple[_ToolCallDelta, ...]:
    raw_calls = delta.get("tool_calls") if delta is not None else None
    if not isinstance(raw_calls, list):
        return ()

    calls: list[_ToolCallDelta] = []
    for raw_call in cast(list[object], raw_calls):
        call = _as_object(raw_call)
        if call is None:
            continue
        index = call.get("index")
        function = _as_object(call.get("function"))
        call_id = call.get("id")
        name = function.get("name") if function is not None else None
        arguments = function.get("arguments") if function is not None else None
        calls.append(
            _ToolCallDelta(
                index=index if isinstance(index, int) else len(calls),
                id=call_id if isinstance(call_id, str) else "",
                name=name if isinstance(name, str) else "",
                arguments=arguments if isinstance(arguments, str) else "",
            )
        )
    return tuple(calls)


def _serialize_message(message: ChatMessage) -> dict[str, object]:
    serialized: dict[str, object] = {"role": message.role, "content": message.content}
    if message.tool_calls:
        serialized["tool_calls"] = [
            {
                "id": tool_call.id,
                "type": "function",
                "function": {"name": tool_call.name, "arguments": tool_call.arguments},
            }
            for tool_call in message.tool_calls
        ]
    if message.tool_call_id is not None:
        serialized["tool_call_id"] = message.tool_call_id
    return serialized


def _serialize_tool(tool: ToolSchema) -> dict[str, object]:
    return {
        "type": "function",
        "function": {
            "name": tool.name,
            "description": tool.description,
            "parameters": tool.parameters,
        },
    }


def _extract_error(body: bytes) -> str:
    try:
        payload = _as_object(json.loads(body))
    except (json.JSONDecodeError, UnicodeDecodeError):
        return "request rejected"

    error = _as_object(payload.get("error")) if payload is not None else None
    message = error.get("message") if error is not None else None
    return message if isinstance(message, str) else "request rejected"


def _as_object(value: object) -> dict[str, object] | None:
    if not isinstance(value, dict):
        return None
    return cast(dict[str, object], value)
