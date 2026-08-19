from collections.abc import Callable, Sequence
from dataclasses import dataclass
from typing import Literal, Protocol

ChatRole = Literal["system", "user", "assistant", "tool"]


@dataclass(frozen=True, slots=True)
class ToolCall:
    """One model-requested function call."""

    id: str
    name: str
    arguments: str


@dataclass(frozen=True, slots=True)
class ChatMessage:
    """A provider-neutral chat message."""

    role: ChatRole
    content: str
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None


@dataclass(frozen=True, slots=True)
class ToolSchema:
    """Provider-neutral JSON schema for one callable tool."""

    name: str
    description: str
    parameters: dict[str, object]


@dataclass(frozen=True, slots=True)
class ModelResponse:
    """A complete model turn assembled from a streamed response."""

    content: str
    tool_calls: tuple[ToolCall, ...]
    finish_reason: str | None


TextCallback = Callable[[str], None]


class ChatProvider(Protocol):
    """Model boundary used by chat and the agent runtime."""

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSchema] = (),
        model: str,
        reasoning_effort: str,
        on_text: TextCallback | None = None,
    ) -> ModelResponse:
        """Return one model turn and optionally report streamed text increments."""
        ...
