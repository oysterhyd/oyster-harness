from collections.abc import AsyncIterator, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

ChatRole = Literal["system", "user", "assistant"]


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A provider-neutral chat message."""

    role: ChatRole
    content: str


class ChatProvider(Protocol):
    """The smallest model interface needed by the current CLI."""

    def stream(self, messages: Sequence[ChatMessage]) -> AsyncIterator[str]:
        """Yield text increments for one model response."""
        ...
