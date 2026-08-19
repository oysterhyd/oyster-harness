"""Model provider boundary for Oyster Harness."""

from oyster_harness.llm.base import ChatMessage, ChatProvider
from oyster_harness.llm.opencode import OpenCodeAPIError, OpenCodeProvider

__all__ = ["ChatMessage", "ChatProvider", "OpenCodeAPIError", "OpenCodeProvider"]
