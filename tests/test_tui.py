from io import StringIO
from pathlib import Path

from rich.console import Console

from oyster_harness.agent import AgentEvent, AgentEventKind, AgentSettings, ReasoningEffort
from oyster_harness.llm.base import ToolCall
from oyster_harness.permissions import PermissionMode
from oyster_harness.tools import ToolResult
from oyster_harness.tui import TerminalUI


def test_banner_and_status_expose_runtime_identity(tmp_path: Path) -> None:
    output = StringIO()
    console = Console(file=output, color_system=None, width=120)
    ui = TerminalUI(console, tmp_path)
    settings = AgentSettings(
        model="hy3",
        reasoning_effort=ReasoningEffort.HIGH,
        permission_mode=PermissionMode.READ_ONLY,
    )

    ui.show_banner()
    ui.show_status(settings, 73)

    rendered = output.getvalue()
    assert "OYSTER" in rendered.replace(" ", "")
    assert "HARNESS" in rendered.replace(" ", "")
    assert "hy3" in rendered
    assert "high" in rendered
    assert "read-only" in rendered
    assert "73% context left" in rendered


def test_tool_completion_updates_the_existing_activity_line(tmp_path: Path) -> None:
    ui = TerminalUI(Console(file=StringIO(), color_system=None), tmp_path)
    call = ToolCall("call_1", "read_file", '{"path":"README.md"}')

    ui.handle_event(
        AgentEvent(AgentEventKind.TOOL_STARTED, "read_file · README.md", tool_call=call)
    )
    ui.handle_event(
        AgentEvent(
            AgentEventKind.TOOL_FINISHED,
            "read_file · README.md",
            tool_call=call,
            tool_result=ToolResult("call_1", "read_file", "contents"),
        )
    )

    assert ui.activity_lines == ("  ✓  read_file · README.md",)
    assert "done" not in ui.activity_lines[0]
