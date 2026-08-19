"""Model provider boundary for Oyster Harness."""

from oyster_harness.llm.base import ChatMessage, ChatProvider, ModelResponse, ToolCall, ToolSchema
from oyster_harness.llm.opencode import OpenCodeAPIError, OpenCodeProvider

__all__ = [
    "ChatMessage",
    "ChatProvider",
    "ModelResponse",
    "OpenCodeAPIError",
    "OpenCodeProvider",
    "ToolCall",
    "ToolSchema",
]
