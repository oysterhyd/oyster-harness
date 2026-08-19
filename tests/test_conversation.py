import asyncio
from collections.abc import AsyncIterator, Sequence

from oyster_harness.conversation import ChatSession
from oyster_harness.llm.base import ChatMessage


class FakeProvider:
    def __init__(self) -> None:
        self.calls: list[tuple[ChatMessage, ...]] = []

    async def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        self.calls.append(tuple(messages))
        yield "hello"
        yield " oyster"


def test_session_keeps_successful_turns() -> None:
    provider = FakeProvider()
    session = ChatSession(provider)

    async def converse() -> list[str]:
        first = [chunk async for chunk in session.reply("first")]
        second = [chunk async for chunk in session.reply("second")]
        return first + second

    chunks = asyncio.run(converse())

    assert chunks == ["hello", " oyster", "hello", " oyster"]
    assert [message.role for message in provider.calls[1]] == [
        "system",
        "user",
        "assistant",
        "user",
    ]
    assert provider.calls[1][2].content == "hello oyster"
