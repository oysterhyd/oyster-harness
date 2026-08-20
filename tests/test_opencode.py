import asyncio

import httpx
import pytest

from oyster_harness.llm.base import ChatMessage, ToolCall, ToolSchema
from oyster_harness.llm.opencode import DEFAULT_MODEL, OpenCodeAPIError, OpenCodeProvider


def test_provider_parses_openai_compatible_stream() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["Authorization"] == "Bearer test-key"
        body = request.content.decode()
        assert f'"model":"{DEFAULT_MODEL}"' in body
        assert '"stream_options":{"include_usage":true}' in body
        content = (
            'data: {"choices":[{"delta":{"content":"hello"}}]}\n\n'
            'data: {"choices":[{"delta":{"content":" oyster"}}]}\n\n'
            'data: {"choices":[],"usage":{"prompt_tokens":37,'
            '"completion_tokens":2,"total_tokens":39}}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=content, headers={"content-type": "text/event-stream"})

    async def request() -> tuple[str, int | None, list[str]]:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenCodeProvider("test-key", client=client)
            streamed: list[str] = []
            response = await provider.complete(
                [ChatMessage(role="user", content="hello")],
                model=DEFAULT_MODEL,
                reasoning_effort="medium",
                on_text=streamed.append,
            )
            return response.content, response.input_tokens, streamed

    assert asyncio.run(request()) == ("hello oyster", 37, ["hello", " oyster"])


def test_provider_assembles_streamed_tool_calls() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = request.content.decode()
        assert '"reasoning_effort":"high"' in body
        assert '"name":"read_file"' in body
        content = (
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,"id":"call_1",'
            '"function":{"name":"read_file","arguments":"{\\"path\\":\\""}}]}}]}\n\n'
            'data: {"choices":[{"delta":{"tool_calls":[{"index":0,'
            '"function":{"arguments":"README.md\\"}"}}]},"finish_reason":"tool_calls"}]}\n\n'
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=content, headers={"content-type": "text/event-stream"})

    async def request() -> ToolCall:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenCodeProvider("test-key", client=client)
            response = await provider.complete(
                [ChatMessage(role="user", content="read")],
                tools=(
                    ToolSchema(
                        "read_file",
                        "Read a file",
                        {"type": "object", "properties": {}},
                    ),
                ),
                model=DEFAULT_MODEL,
                reasoning_effort="high",
            )
            assert response.finish_reason == "tool_calls"
            return response.tool_calls[0]

    assert asyncio.run(request()) == ToolCall("call_1", "read_file", '{"path":"README.md"}')


def test_provider_reports_api_error_without_raw_body() -> None:
    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "invalid credentials"}})

    async def request() -> None:
        transport = httpx.MockTransport(handler)
        async with httpx.AsyncClient(transport=transport) as client:
            provider = OpenCodeProvider("test-key", client=client)
            await provider.complete(
                [ChatMessage(role="user", content="hello")],
                model=DEFAULT_MODEL,
                reasoning_effort="medium",
            )

    with pytest.raises(OpenCodeAPIError, match="HTTP 401: invalid credentials"):
        asyncio.run(request())
