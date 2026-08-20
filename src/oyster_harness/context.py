from dataclasses import dataclass, field, replace
from functools import cache

import tiktoken

from oyster_harness.llm.base import ChatMessage
from oyster_harness.tools import ToolResult

TOKEN_ENCODING = "o200k_base"


@dataclass(slots=True)
class WorkingMemory:
    """Small deterministic memory kept when old conversation turns are compacted."""

    observations: list[str] = field(default_factory=lambda: list[str]())
    failures: list[str] = field(default_factory=lambda: list[str]())
    modified_files: set[str] = field(default_factory=lambda: set[str]())

    def record(self, result: ToolResult) -> None:
        first_line = result.content.splitlines()[0] if result.content else "(no output)"
        note = f"{result.name}: {_clip_chars(first_line, 240)}"
        target = self.failures if result.is_error else self.observations
        target.append(note)
        del target[:-12]
        if result.modified_path is not None:
            self.modified_files.add(result.modified_path)

    def render(self) -> str:
        sections: list[str] = []
        if self.observations:
            sections.append("Recent observations:\n- " + "\n- ".join(self.observations[-6:]))
        if self.failures:
            sections.append("Recent failures:\n- " + "\n- ".join(self.failures[-4:]))
        if self.modified_files:
            sections.append("Modified files:\n- " + "\n- ".join(sorted(self.modified_files)))
        return "\n\n".join(sections) or "No retained working memory."


class ContextManager:
    """Bound model input with a model-neutral tokenizer estimate."""

    def __init__(
        self,
        max_tokens: int = 20_000,
        max_tool_result_tokens: int = 4_000,
    ) -> None:
        if max_tokens < 512:
            raise ValueError("max_tokens must be at least 512")
        self.max_tokens = max_tokens
        self.max_tool_result_tokens = min(max_tool_result_tokens, max_tokens // 2)
        self.memory = WorkingMemory()

    def build(self, messages: tuple[ChatMessage, ...]) -> tuple[ChatMessage, ...]:
        if not messages:
            return ()
        system = self._trim(messages[0])
        blocks = tuple(
            tuple(self._trim(message) for message in block)
            for block in self._turn_blocks(messages[1:])
        )
        selected: list[tuple[ChatMessage, ...]] = []
        budget = self.max_tokens - _message_tokens(system)

        for block in reversed(blocks):
            size = sum(_message_tokens(message) for message in block)
            if selected and size > budget:
                break
            selected.append(block if size <= budget else _fit_block(block, budget))
            budget -= size
            if budget <= 0:
                break

        selected.reverse()
        flattened = tuple(message for block in selected for message in block)
        dropped = len(selected) < len(blocks)
        if not dropped:
            return (system, *flattened)

        summary = ChatMessage(
            role="system",
            content="Earlier conversation was compacted.\n\n" + self.memory.render(),
        )
        while len(selected) > 1 and (
            _message_tokens(system)
            + _message_tokens(summary)
            + sum(_message_tokens(message) for message in flattened)
            > self.max_tokens
        ):
            selected.pop(0)
            flattened = tuple(message for block in selected for message in block)
        if (
            selected
            and _message_tokens(system)
            + _message_tokens(summary)
            + sum(_message_tokens(message) for message in flattened)
            > self.max_tokens
        ):
            remaining = self.max_tokens - _message_tokens(system) - _message_tokens(summary)
            selected[-1] = _fit_block(selected[-1], remaining)
            flattened = tuple(message for block in selected for message in block)
        return (system, summary, *flattened)

    def record(self, result: ToolResult) -> None:
        self.memory.record(result)

    def estimate(self, messages: tuple[ChatMessage, ...]) -> int:
        return sum(_message_tokens(message) for message in self.build(messages))

    def remaining_percentage(self, messages: tuple[ChatMessage, ...]) -> int:
        """Return the managed context window remaining, rounded to a whole percent."""
        return self.remaining_percentage_for_tokens(self.estimate(messages))

    def remaining_percentage_for_tokens(self, used_tokens: int) -> int:
        """Return the remaining percentage for provider-reported input usage."""
        used = min(max(used_tokens, 0), self.max_tokens)
        remaining = self.max_tokens - used
        return (remaining * 100 + self.max_tokens // 2) // self.max_tokens

    def _trim(self, message: ChatMessage) -> ChatMessage:
        if (
            message.role != "tool"
            or count_text_tokens(message.content) <= self.max_tool_result_tokens
        ):
            return message
        return replace(
            message,
            content=_clip_tokens(message.content, self.max_tool_result_tokens),
        )

    @staticmethod
    def _turn_blocks(messages: tuple[ChatMessage, ...]) -> tuple[tuple[ChatMessage, ...], ...]:
        blocks: list[list[ChatMessage]] = []
        for message in messages:
            if message.role == "user" or not blocks:
                blocks.append([])
            blocks[-1].append(message)
        return tuple(tuple(block) for block in blocks)


def count_text_tokens(value: str) -> int:
    """Count tokens with the explicit model-neutral encoding used for budgeting."""
    return len(_encoding().encode(value, disallowed_special=()))


def _fit_block(block: tuple[ChatMessage, ...], budget: int) -> tuple[ChatMessage, ...]:
    fixed_tokens = sum(_message_tokens(replace(message, content="")) for message in block)
    content_budget = max(0, budget - fixed_tokens)
    messages_left = len(block)
    fitted: list[ChatMessage] = []
    for message in block:
        share = max(0, content_budget // messages_left)
        content = message.content
        if count_text_tokens(content) > share:
            content = _clip_tokens(content, share)
        fitted.append(replace(message, content=content))
        content_budget -= count_text_tokens(content)
        messages_left -= 1
    return tuple(fitted)


def _message_tokens(message: ChatMessage) -> int:
    tool_call_tokens = sum(
        count_text_tokens(call.name)
        + count_text_tokens(call.arguments)
        + count_text_tokens(call.id)
        for call in message.tool_calls
    )
    return (
        count_text_tokens(message.role) + count_text_tokens(message.content) + tool_call_tokens + 4
    )


def _clip_chars(value: str, limit: int) -> str:
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _clip_tokens(value: str, limit: int) -> str:
    if limit <= 0:
        return ""
    encoding = _encoding()
    tokens = encoding.encode(value, disallowed_special=())
    if len(tokens) <= limit:
        return value
    marker = "\n... compacted ...\n"
    marker_tokens = encoding.encode(marker)
    if len(marker_tokens) >= limit:
        return encoding.decode(tokens[:limit])
    remaining = limit - len(marker_tokens)
    left = remaining // 2
    right = remaining - left
    return encoding.decode(tokens[:left]) + marker + encoding.decode(tokens[-right:])


@cache
def _encoding() -> tiktoken.Encoding:
    return tiktoken.get_encoding(TOKEN_ENCODING)
