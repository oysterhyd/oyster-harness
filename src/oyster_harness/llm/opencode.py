import json
from collections.abc import AsyncIterator, Sequence
from typing import cast

import httpx

from oyster_harness.llm.base import ChatMessage

DEFAULT_CHAT_ENDPOINT = "https://opencode.ai/zen/go/v1/chat/completions"
DEFAULT_MODEL = "hy3"


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

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        request: dict[str, object] = {
            "model": DEFAULT_MODEL,
            "messages": [
                {"role": message.role, "content": message.content} for message in messages
            ],
            "stream": True,
        }
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

        if self._client is not None:
            async for chunk in self._stream_with_client(self._client, headers, request):
                yield chunk
            return

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                async for chunk in self._stream_with_client(client, headers, request):
                    yield chunk
        except httpx.HTTPError as exc:
            raise OpenCodeAPIError(f"OpenCode Go request failed: {type(exc).__name__}.") from exc

    async def _stream_with_client(
        self,
        client: httpx.AsyncClient,
        headers: dict[str, str],
        request: dict[str, object],
    ) -> AsyncIterator[str]:
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
                    return

                chunk = _extract_text(data)
                if chunk:
                    yield chunk


def _extract_text(data: str) -> str:
    try:
        payload = _as_object(json.loads(data))
    except json.JSONDecodeError as exc:
        raise OpenCodeAPIError("OpenCode Go returned an invalid stream event.") from exc

    if payload is None:
        return ""

    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return ""

    choice = _as_object(cast(object, choices[0]))
    delta = _as_object(choice.get("delta")) if choice is not None else None
    content = delta.get("content") if delta is not None else None
    return content if isinstance(content, str) else ""


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
