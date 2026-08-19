import asyncio
import json
import os
from pathlib import Path

from oyster_harness.llm.base import ToolCall
from oyster_harness.tools import ToolRegistry


def _execute(registry: ToolRegistry, name: str, arguments: dict[str, object]):
    call = ToolCall("call_1", name, json.dumps(arguments))
    return asyncio.run(registry.execute(call))


def test_file_tools_stay_inside_workspace_and_edit_exact_text(tmp_path: Path) -> None:
    source = tmp_path / "src" / "sample.py"
    source.parent.mkdir()
    source.write_text("VALUE = 1\n", encoding="utf-8")
    registry = ToolRegistry(tmp_path)

    listed = _execute(registry, "list_dir", {"path": "src"})
    read = _execute(registry, "read_file", {"path": "src/sample.py"})
    edited = _execute(
        registry,
        "edit_file",
        {"path": "src/sample.py", "old_text": "VALUE = 1", "new_text": "VALUE = 2"},
    )
    escaped = _execute(registry, "read_file", {"path": "../secret.txt"})

    assert listed.content == "sample.py"
    assert "1: VALUE = 1" in read.content
    assert edited.modified_path == "src/sample.py"
    assert source.read_text(encoding="utf-8") == "VALUE = 2\n"
    assert escaped.is_error
    assert "outside the workspace" in escaped.content


def test_grep_finds_workspace_text(tmp_path: Path) -> None:
    (tmp_path / "notes.txt").write_text("a pearl grows here\n", encoding="utf-8")

    result = _execute(ToolRegistry(tmp_path), "grep", {"pattern": "pearl"})

    assert not result.is_error
    assert "notes.txt:1" in result.content


def test_shell_runs_in_requested_runtime(tmp_path: Path) -> None:
    shell = "pwsh" if os.name == "nt" else "bash"
    command = "Write-Output oyster" if shell == "pwsh" else "printf oyster"

    result = _execute(
        ToolRegistry(tmp_path),
        "shell",
        {"command": command, "shell": shell, "timeout_seconds": 5},
    )

    assert not result.is_error
    assert json.loads(result.content)["stdout"].strip() == "oyster"
