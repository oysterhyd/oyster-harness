import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest

from oyster_harness.llm.base import ChatMessage
from oyster_harness.llm.opencode import DEFAULT_MODEL, OpenCodeAPIError, OpenCodeProvider


async def _collect(stream: AsyncIterator[str]) -> list[str]:
    return [chunk async for chunk in stream]


def test_provider_parses_openai_compatible_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        assert f'"model":"{DEFAULT_MODEL}"' in request.content.decode()
        content = (
            'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":" oyster"}}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=content, headers={"content-type": "text/event-stream"})

    async def request() -> list[str]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenCodeProvider("test-key", client=client)
            return await _collect(provider.stream([ChatMessage(role="user", content="hello")]))

    assert asyncio.run(request()) == ["hello", " oyster"]


def test_provider_reports_api_error_without_raw_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid credentials"}})

    async def request() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenCodeProvider("test-key", client=client)
            await _collect(provider.stream([ChatMessage(role="user", content="hello")]))

    with pytest.raises(OpenCodeAPIError, match="HTTP 401: invalid credentials"):
        asyncio.run(request())
