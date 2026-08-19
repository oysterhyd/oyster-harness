from collections.abc import AsyncIterator

from oyster_harness.llm.base import ChatMessage, ChatProvider

DEFAULT_SYSTEM_PROMPT = """You are Oyster, a concise coding assistant.
State uncertainty instead of inventing context. Do not claim to have inspected or changed files
unless their contents or tool results were actually provided."""


class ChatSession:
    """Keep the message history for one interactive CLI session."""

    def __init__(
        self,
        provider: ChatProvider,
        system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    ) -> None:
        self._provider = provider
        self._messages = [ChatMessage(role="system", content=system_prompt)]

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        return tuple(self._messages)

    async def reply(self, user_input: str) -> AsyncIterator[str]:
        prompt = user_input.strip()
        if not prompt:
            raise ValueError("User input cannot be empty.")

        self._messages.append(ChatMessage(role="user", content=prompt))
        chunks: list[str] = []

        try:
            async for chunk in self._provider.stream(self.messages):
                chunks.append(chunk)
                yield chunk
        except Exception:
            self._messages.pop()
            raise

        self._messages.append(ChatMessage(role="assistant", content="".join(chunks)))
