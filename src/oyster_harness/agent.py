import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from enum import StrEnum
from pathlib import Path
from typing import cast

from oyster_harness.context import ContextManager
from oyster_harness.llm.base import ChatMessage, ChatProvider, ToolCall
from oyster_harness.llm.opencode import DEFAULT_MODEL, model_context_window
from oyster_harness.permissions import PermissionDecision, PermissionManager, PermissionMode
from oyster_harness.tools import ToolRegistry, ToolResult

DEFAULT_MAX_ITERATIONS = 12

AGENT_SYSTEM_PROMPT = """You are Oyster, the coding agent inside Oyster Harness.
Oyster Harness is a lightweight, opinionated terminal coding agent that grows around its
user's workflow. When asked about your identity or model, use the authoritative runtime
identity below instead of guessing from training knowledge.

Use tools to inspect facts before claiming anything about the workspace. Continue the
observe-reason-act loop until you can answer the user or have a concrete blocker.

Tool rules:
- Prefer list_dir, grep, and read_file before editing.
- Use edit_file for a small exact replacement and write_file only when creating or replacing a file.
- Use shell with either pwsh or bash, choose commands appropriate for the current operating system.
- Treat denied tool results as hard policy; explain the limitation or choose a safer action.
- Keep the final answer concise and report what you verified.
"""


class ReasoningEffort(StrEnum):
    NONE = "none"
    MINIMAL = "minimal"
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    XHIGH = "xhigh"


@dataclass(slots=True)
class AgentSettings:
    model: str = DEFAULT_MODEL
    reasoning_effort: ReasoningEffort = ReasoningEffort.MEDIUM
    permission_mode: PermissionMode = PermissionMode.ASK
    max_iterations: int = DEFAULT_MAX_ITERATIONS
    context_tokens: int | None = None


class AgentEventKind(StrEnum):
    MODEL_TEXT = "model_text"
    TOOL_STARTED = "tool_started"
    TOOL_FINISHED = "tool_finished"
    PERMISSION_REQUESTED = "permission_requested"


@dataclass(frozen=True, slots=True)
class AgentEvent:
    kind: AgentEventKind
    text: str
    tool_call: ToolCall | None = None
    tool_result: ToolResult | None = None


@dataclass(frozen=True, slots=True)
class AgentResult:
    content: str
    iterations: int
    tool_calls: int
    stop_reason: str
    context_tokens: int


EventHandler = Callable[[AgentEvent], None]
ApprovalHandler = Callable[[ToolCall], Awaitable[bool]]


class AgentSession:
    """Stateful model/tool loop for one terminal session."""

    def __init__(
        self,
        provider: ChatProvider,
        workspace: Path,
        settings: AgentSettings | None = None,
        *,
        registry: ToolRegistry | None = None,
        system_prompt: str = AGENT_SYSTEM_PROMPT,
    ) -> None:
        self.settings = settings or AgentSettings()
        self._provider = provider
        self._registry = registry or ToolRegistry(workspace)
        self._permissions = PermissionManager(self.settings.permission_mode)
        self._context = ContextManager(self._configured_context_window())
        self._last_input_tokens: int | None = None
        self._workspace = workspace.resolve()
        self._base_system_prompt = system_prompt.rstrip()
        self._system_message = self._make_system_message()
        self._messages = [self._system_message]

    @property
    def messages(self) -> tuple[ChatMessage, ...]:
        return tuple(self._messages)

    @property
    def context_tokens(self) -> int:
        return (
            self._last_input_tokens
            if self._last_input_tokens is not None
            else self._context.estimate(self.messages)
        )

    @property
    def context_window_tokens(self) -> int:
        return self._context.max_tokens

    @property
    def context_left_percent(self) -> int:
        if self._last_input_tokens is not None:
            return self._context.remaining_percentage_for_tokens(self._last_input_tokens)
        return self._context.remaining_percentage(self.messages)

    def set_model(self, model: str) -> None:
        normalized = model.strip()
        if not normalized:
            raise ValueError("Model cannot be empty.")
        self.settings.model = normalized
        if self.settings.context_tokens is None:
            memory = self._context.memory
            self._context = ContextManager(model_context_window(normalized))
            self._context.memory = memory
            self._messages = list(self._context.build(self.messages))
        self._last_input_tokens = None
        self._refresh_system_message()

    def set_reasoning_effort(self, effort: ReasoningEffort) -> None:
        self.settings.reasoning_effort = effort
        self._last_input_tokens = None
        self._refresh_system_message()

    def set_permission_mode(self, mode: PermissionMode) -> None:
        self.settings.permission_mode = mode
        self._permissions.mode = mode
        self._last_input_tokens = None
        self._refresh_system_message()

    def clear(self) -> None:
        """Clear conversation history and working memory without changing runtime settings."""
        self._context = ContextManager(self._configured_context_window())
        self._last_input_tokens = None
        self._system_message = self._make_system_message()
        self._messages = [self._system_message]

    async def run(
        self,
        prompt: str,
        *,
        on_event: EventHandler | None = None,
        approve: ApprovalHandler | None = None,
    ) -> AgentResult:
        user_input = prompt.strip()
        if not user_input:
            raise ValueError("User input cannot be empty.")
        self._refresh_system_message()
        self._messages.append(ChatMessage(role="user", content=user_input))
        tool_call_count = 0

        for iteration in range(1, self.settings.max_iterations + 1):
            response = await self._provider.complete(
                self._context.build(self.messages),
                tools=self._registry.schemas,
                model=self.settings.model,
                reasoning_effort=self.settings.reasoning_effort.value,
                on_text=lambda text: _emit(
                    on_event,
                    AgentEvent(AgentEventKind.MODEL_TEXT, text),
                ),
            )
            self._last_input_tokens = response.input_tokens
            self._messages.append(
                ChatMessage(
                    role="assistant",
                    content=response.content,
                    tool_calls=response.tool_calls,
                )
            )

            if not response.tool_calls:
                content = response.content or "The model returned an empty response."
                self._compact_history()
                return AgentResult(
                    content,
                    iteration,
                    tool_call_count,
                    response.finish_reason or "complete",
                    self.context_tokens,
                )

            for call in response.tool_calls:
                tool_call_count += 1
                _emit(
                    on_event,
                    AgentEvent(AgentEventKind.TOOL_STARTED, _summarize_call(call), call),
                )
                result = await self._execute_call(call, approve, on_event)
                self._context.record(result)
                observation = result.content
                if result.is_error:
                    observation = f"ERROR: {observation}"
                self._messages.append(
                    ChatMessage(role="tool", content=observation, tool_call_id=call.id)
                )
                _emit(
                    on_event,
                    AgentEvent(
                        AgentEventKind.TOOL_FINISHED,
                        _summarize_result(result),
                        call,
                        result,
                    ),
                )

        content = (
            f"Stopped after {self.settings.max_iterations} iterations to avoid an unbounded loop."
        )
        self._messages.append(ChatMessage(role="assistant", content=content))
        self._compact_history()
        return AgentResult(
            content,
            self.settings.max_iterations,
            tool_call_count,
            "max_iterations",
            self.context_tokens,
        )

    async def _execute_call(
        self,
        call: ToolCall,
        approve: ApprovalHandler | None,
        on_event: EventHandler | None,
    ) -> ToolResult:
        decision = self._permissions.decide(call)
        if decision is PermissionDecision.DENY:
            return ToolResult(call.id, call.name, "Denied by the active permission policy.", True)
        if decision is PermissionDecision.ASK:
            _emit(
                on_event,
                AgentEvent(AgentEventKind.PERMISSION_REQUESTED, _summarize_call(call), call),
            )
            allowed = await approve(call) if approve is not None else False
            if not allowed:
                return ToolResult(call.id, call.name, "User did not approve this tool call.", True)
        return await self._registry.execute(call)

    def _compact_history(self) -> None:
        self._messages = list(self._context.build(self.messages))

    def _refresh_system_message(self) -> None:
        self._system_message = self._make_system_message()
        if self._messages:
            self._messages[0] = self._system_message

    def _make_system_message(self) -> ChatMessage:
        runtime_identity = (
            "\n\nAuthoritative runtime identity:\n"
            "- Product: Oyster Harness\n"
            "- Agent name: Oyster\n"
            "- Provider: OpenCode Go\n"
            f"- Active model ID: {self.settings.model}\n"
            f"- Reasoning effort: {self.settings.reasoning_effort.value}\n"
            f"- Permission mode: {self.settings.permission_mode.value}\n"
            f"- Workspace root: {self._workspace}\n"
        )
        return ChatMessage(role="system", content=self._base_system_prompt + runtime_identity)

    def _configured_context_window(self) -> int:
        if self.settings.context_tokens is not None:
            return self.settings.context_tokens
        return model_context_window(self.settings.model)


def _emit(handler: EventHandler | None, event: AgentEvent) -> None:
    if handler is not None:
        handler(event)


def _summarize_call(call: ToolCall) -> str:
    try:
        parsed = json.loads(call.arguments)
    except json.JSONDecodeError:
        return call.name
    if not isinstance(parsed, dict):
        return call.name
    arguments = cast(dict[str, object], parsed)
    for key in ("path", "pattern", "command"):
        value = arguments.get(key)
        if isinstance(value, str):
            single_line = " ".join(value.splitlines())
            return f"{call.name} · {single_line[:100]}"
    return call.name


def _summarize_result(result: ToolResult) -> str:
    detail = result.content.splitlines()[0][:120] if result.content else "no output"
    return f"{result.name} · {detail}"
