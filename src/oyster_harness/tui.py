from dataclasses import dataclass
from pathlib import Path

from rich import box
from rich.align import Align
from rich.console import Console, Group, RenderableType
from rich.live import Live
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm
from rich.text import Text

from oyster_harness.agent import AgentEvent, AgentEventKind, AgentResult, AgentSettings
from oyster_harness.llm.base import ToolCall

LOGO = """\
 ██████╗ ██╗   ██╗███████╗████████╗███████╗██████╗
██╔═══██╗╚██╗ ██╔╝██╔════╝╚══██╔══╝██╔════╝██╔══██╗
██║   ██║ ╚████╔╝ ███████╗   ██║   █████╗  ██████╔╝
██║   ██║  ╚██╔╝  ╚════██║   ██║   ██╔══╝  ██╔══██╗
╚██████╔╝   ██║   ███████║   ██║   ███████╗██║  ██║
 ╚═════╝    ╚═╝   ╚══════╝   ╚═╝   ╚══════╝╚═╝  ╚═╝"""


@dataclass(slots=True)
class _ToolActivity:
    text: str
    marker: str = "◌"
    error_detail: str = ""

    def render(self) -> str:
        detail = f" · {self.error_detail}" if self.error_detail else ""
        return f"  {self.marker}  {self.text}{detail}"


class TerminalUI:
    """Rich presentation for a stateful Oyster session."""

    def __init__(self, console: Console, workspace: Path) -> None:
        self.console = console
        self.workspace = workspace.resolve()
        self._live: Live | None = None
        self._model_text = ""
        self._activity: list[_ToolActivity] = []
        self._activity_index: dict[str, int] = {}
        self._status = Text()

    @property
    def activity_lines(self) -> tuple[str, ...]:
        return tuple(activity.render() for activity in self._activity)

    def show_banner(self) -> None:
        logo = Text(LOGO, style="bold #7dd3fc")
        harness = Text("O Y S T E R   H A R N E S S", style="bold #c4b5fd")
        tagline = Text("◉  a coding agent that grows around your workflow", style="#94a3b8")
        content = Group(Align.center(logo), Align.center(harness), Align.center(tagline))
        self.console.print(
            Panel(
                content,
                border_style="#334155",
                box=box.ROUNDED,
                padding=(1, 2),
            )
        )
        self.console.print(Align.center(Text("/help commands  ·  /exit leave", style="dim")))

    def show_user(self, message: str) -> None:
        self.console.print(
            Panel(
                Text(message),
                title="[bold #67e8f9] You [/bold #67e8f9]",
                title_align="left",
                border_style="#0e7490",
                box=box.ROUNDED,
                padding=(0, 1),
            )
        )

    def begin_reply(self, settings: AgentSettings, context_left_percent: int) -> None:
        self._model_text = ""
        self._activity = []
        self._activity_index = {}
        self._status = self._status_text(settings, context_left_percent)
        self._live = Live(
            self._live_renderable("Thinking…"),
            console=self.console,
            auto_refresh=False,
            transient=True,
        )
        self._live.start(refresh=True)

    def handle_event(self, event: AgentEvent) -> None:
        if event.kind is AgentEventKind.MODEL_TEXT:
            self._model_text += event.text
        elif event.kind is AgentEventKind.TOOL_STARTED:
            self._start_tool(event)
        elif event.kind is AgentEventKind.TOOL_FINISHED:
            self._finish_tool(event)
        self._refresh()

    def end_reply(self, result: AgentResult) -> None:
        if not self._model_text:
            self._model_text = result.content
        final_panel = self._reply_panel()
        if self._live is not None:
            self._live.stop()
            self._live = None
        self.console.print(final_panel)

    async def approve(self, call: ToolCall) -> bool:
        running_live = self._live is not None
        if self._live is not None:
            self._live.stop()
        self.console.print(
            Panel(
                Text(call.arguments[:2_000], style="#cbd5e1"),
                title=f"[bold yellow] Permission · {call.name} [/bold yellow]",
                border_style="yellow",
                box=box.ROUNDED,
            )
        )
        allowed = Confirm.ask("Allow this tool call?", default=False, console=self.console)
        if running_live and self._live is not None:
            self._live.start(refresh=True)
        return allowed

    def status_plain(self, settings: AgentSettings, context_left_percent: int) -> str:
        return (
            f"◉ {self.workspace.name} · model {settings.model} · "
            f"effort {settings.reasoning_effort.value} · "
            f"perms {settings.permission_mode.value} · {context_left_percent}% context left"
        )

    def show_status(self, settings: AgentSettings, context_left_percent: int) -> None:
        self.console.print(
            Panel(
                self._status_text(settings, context_left_percent),
                box=box.SIMPLE,
                border_style="#334155",
                padding=(0, 0),
            )
        )

    def show_notice(self, message: str, *, style: str = "cyan") -> None:
        self.console.print(Panel(message, border_style=style, box=box.ROUNDED, padding=(0, 1)))

    def show_error(self, message: str) -> None:
        self.abort_reply()
        self.console.print(Panel(message, title="Error", border_style="red", box=box.ROUNDED))

    def abort_reply(self) -> None:
        if self._live is not None:
            self._live.stop()
            self._live = None

    def _start_tool(self, event: AgentEvent) -> None:
        call_id = (
            event.tool_call.id if event.tool_call is not None else f"tool-{len(self._activity)}"
        )
        self._activity_index[call_id] = len(self._activity)
        self._activity.append(_ToolActivity(event.text))

    def _finish_tool(self, event: AgentEvent) -> None:
        call_id = event.tool_call.id if event.tool_call is not None else ""
        index = self._activity_index.get(call_id)
        if index is None:
            self._activity.append(_ToolActivity(event.text, marker="✓"))
            return
        activity = self._activity[index]
        failed = event.tool_result is not None and event.tool_result.is_error
        activity.marker = "×" if failed else "✓"
        if failed and event.tool_result is not None:
            activity.error_detail = event.tool_result.content.splitlines()[0][:100]

    def _refresh(self) -> None:
        if self._live is not None:
            self._live.update(self._live_renderable(), refresh=True)

    def _live_renderable(self, placeholder: str = "") -> Group:
        return Group(self._status, self._reply_panel(placeholder))

    def _reply_panel(self, placeholder: str = "") -> Panel:
        renderables: list[RenderableType] = []
        if self._activity:
            renderables.append(Text("\n".join(self.activity_lines), style="#94a3b8"))
        if self._model_text:
            renderables.append(Markdown(self._model_text))
        elif placeholder:
            renderables.append(Text(placeholder, style="italic #94a3b8"))
        return Panel(
            Group(*renderables),
            title="[bold #a5b4fc] Oyster [/bold #a5b4fc]",
            title_align="left",
            border_style="#6366f1",
            box=box.ROUNDED,
            padding=(0, 1),
        )

    def _status_text(self, settings: AgentSettings, context_left_percent: int) -> Text:
        status = Text()
        status.append(" ◉ ", style="bold #67e8f9")
        status.append(self.workspace.name, style="bold #e2e8f0")
        status.append(" · model ", style="dim")
        status.append(settings.model, style="bold #93c5fd")
        status.append(" · effort ", style="dim")
        status.append(settings.reasoning_effort.value, style="bold #c4b5fd")
        status.append(" · perms ", style="dim")
        status.append(settings.permission_mode.value, style="bold #fbbf24")
        status.append(" · ", style="dim")
        status.append(f"{context_left_percent}% context left", style="#86efac")
        return status
