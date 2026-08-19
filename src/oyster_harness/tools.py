import asyncio
import json
import os
import shutil
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, cast

from oyster_harness.llm.base import ToolCall, ToolSchema

MAX_TOOL_OUTPUT_CHARS = 20_000


@dataclass(frozen=True, slots=True)
class ToolResult:
    """Observation returned to the model after one tool call."""

    call_id: str
    name: str
    content: str
    is_error: bool = False
    modified_path: str | None = None


class Tool(Protocol):
    name: str
    description: str
    parameters: dict[str, object]

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        """Execute validated JSON arguments inside the workspace."""
        ...


class ToolRegistry:
    """Small explicit registry for the built-in coding tools."""

    def __init__(self, workspace: Path, tools: Sequence[Tool] | None = None) -> None:
        root = workspace.resolve()
        builtins: Sequence[Tool] = tools or (
            ListDirTool(root),
            ReadFileTool(root),
            GrepTool(root),
            EditFileTool(root),
            WriteFileTool(root),
            ShellTool(root),
        )
        self._tools = {tool.name: tool for tool in builtins}

    @property
    def schemas(self) -> tuple[ToolSchema, ...]:
        return tuple(
            ToolSchema(tool.name, tool.description, tool.parameters)
            for tool in self._tools.values()
        )

    async def execute(self, call: ToolCall) -> ToolResult:
        tool = self._tools.get(call.name)
        if tool is None:
            return ToolResult(call.id, call.name, f"Unknown tool: {call.name}", True)
        try:
            parsed = json.loads(call.arguments)
        except json.JSONDecodeError as exc:
            return ToolResult(call.id, call.name, f"Invalid JSON arguments: {exc.msg}", True)
        if not isinstance(parsed, dict):
            return ToolResult(call.id, call.name, "Tool arguments must be a JSON object.", True)
        try:
            result = await tool.execute(cast(dict[str, object], parsed))
        except (OSError, UnicodeError, ValueError) as exc:
            return ToolResult(call.id, call.name, str(exc), True)
        return ToolResult(
            call.id,
            result.name,
            result.content,
            result.is_error,
            result.modified_path,
        )


class _WorkspaceTool:
    def __init__(self, workspace: Path) -> None:
        self._workspace = workspace

    def _path(self, value: object, *, default: str | None = None) -> Path:
        if value is None and default is not None:
            raw_path = default
        elif isinstance(value, str) and value.strip():
            raw_path = value
        else:
            raise ValueError("path must be a non-empty string")

        candidate = (self._workspace / raw_path).resolve()
        if not candidate.is_relative_to(self._workspace):
            raise ValueError("Path is outside the workspace.")
        return candidate

    def _relative(self, path: Path) -> str:
        return path.relative_to(self._workspace).as_posix() or "."


class ListDirTool(_WorkspaceTool):
    name = "list_dir"
    description = "List the immediate files and directories at a workspace-relative path."
    parameters: dict[str, object] = {
        "type": "object",
        "properties": {"path": {"type": "string", "description": "Defaults to ."}},
        "additionalProperties": False,
    }

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        path = self._path(arguments.get("path"), default=".")
        if not path.is_dir():
            raise ValueError(f"Not a directory: {self._relative(path)}")
        entries = sorted(path.iterdir(), key=lambda item: (not item.is_dir(), item.name.lower()))
        lines = [f"{entry.name}/" if entry.is_dir() else entry.name for entry in entries[:200]]
        if len(entries) > 200:
            lines.append(f"... {len(entries) - 200} more entries")
        return ToolResult("", self.name, "\n".join(lines) or "(empty directory)")


class ReadFileTool(_WorkspaceTool):
    name = "read_file"
    description = (
        "Read a UTF-8 text file with line numbers; use line_start and line_end for ranges."
    )
    parameters: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "line_start": {"type": "integer", "minimum": 1},
            "line_end": {"type": "integer", "minimum": 1},
        },
        "required": ["path"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        path = self._path(arguments.get("path"))
        if not path.is_file():
            raise ValueError(f"Not a file: {self._relative(path)}")
        start = _positive_int(arguments.get("line_start"), 1, "line_start")
        end = _positive_int(arguments.get("line_end"), start + 399, "line_end")
        if end < start:
            raise ValueError("line_end must be greater than or equal to line_start")
        lines = path.read_text(encoding="utf-8").splitlines()
        selected = lines[start - 1 : end]
        rendered = "\n".join(f"{number:>5}: {line}" for number, line in enumerate(selected, start))
        header = f"{self._relative(path)} (lines {start}-{min(end, len(lines))} of {len(lines)})"
        return ToolResult("", self.name, _limit_output(f"{header}\n{rendered}"))


class GrepTool(_WorkspaceTool):
    name = "grep"
    description = "Search workspace text with ripgrep regular expressions."
    parameters: dict[str, object] = {
        "type": "object",
        "properties": {
            "pattern": {"type": "string"},
            "path": {"type": "string", "description": "Defaults to ."},
            "glob": {"type": "string", "description": "Optional file glob such as *.py"},
        },
        "required": ["pattern"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        pattern = _string(arguments.get("pattern"), "pattern")
        path = self._path(arguments.get("path"), default=".")
        command = ["rg", "--line-number", "--color", "never", "--hidden", "--glob", "!.git/**"]
        file_glob = arguments.get("glob")
        if file_glob is not None:
            command.extend(("--glob", _string(file_glob, "glob")))
        command.extend((pattern, self._relative(path)))
        returncode, stdout, stderr = await _run_process(command, self._workspace, 15.0)
        if returncode == 1:
            return ToolResult("", self.name, "No matches.")
        if returncode != 0:
            return ToolResult("", self.name, _limit_output(stderr or stdout), True)
        return ToolResult("", self.name, _limit_output(stdout))


class EditFileTool(_WorkspaceTool):
    name = "edit_file"
    description = "Replace one exact text occurrence in an existing UTF-8 file."
    parameters: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old_text": {"type": "string"},
            "new_text": {"type": "string"},
        },
        "required": ["path", "old_text", "new_text"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        path = self._path(arguments.get("path"))
        if not path.is_file():
            raise ValueError(f"Not a file: {self._relative(path)}")
        old_text = _string(arguments.get("old_text"), "old_text", allow_empty=False)
        new_text = _string(arguments.get("new_text"), "new_text", allow_empty=True)
        content = path.read_text(encoding="utf-8")
        occurrences = content.count(old_text)
        if occurrences != 1:
            raise ValueError(f"old_text must match exactly once; found {occurrences} matches")
        _atomic_write(path, content.replace(old_text, new_text, 1))
        relative = self._relative(path)
        return ToolResult("", self.name, f"Updated {relative}", modified_path=relative)


class WriteFileTool(_WorkspaceTool):
    name = "write_file"
    description = "Create or replace a UTF-8 file inside the workspace."
    parameters: dict[str, object] = {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "content": {"type": "string"},
        },
        "required": ["path", "content"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        path = self._path(arguments.get("path"))
        content = _string(arguments.get("content"), "content", allow_empty=True)
        path.parent.mkdir(parents=True, exist_ok=True)
        _atomic_write(path, content)
        relative = self._relative(path)
        return ToolResult("", self.name, f"Wrote {relative}", modified_path=relative)


class ShellTool(_WorkspaceTool):
    name = "shell"
    description = "Run a command in bash or PowerShell 7 inside the workspace."
    parameters: dict[str, object] = {
        "type": "object",
        "properties": {
            "command": {"type": "string"},
            "shell": {"type": "string", "enum": ["bash", "pwsh"]},
            "cwd": {"type": "string", "description": "Workspace-relative; defaults to ."},
            "timeout_seconds": {"type": "integer", "minimum": 1, "maximum": 300},
        },
        "required": ["command", "shell"],
        "additionalProperties": False,
    }

    async def execute(self, arguments: Mapping[str, object]) -> ToolResult:
        command = _string(arguments.get("command"), "command")
        shell = _string(arguments.get("shell"), "shell")
        cwd = self._path(arguments.get("cwd"), default=".")
        if not cwd.is_dir():
            raise ValueError(f"Not a directory: {self._relative(cwd)}")
        timeout = _positive_int(arguments.get("timeout_seconds"), 60, "timeout_seconds")
        timeout = min(timeout, 300)
        executable = shutil.which(shell)
        if executable is None:
            raise ValueError(f"Shell executable is not available: {shell}")
        shell_args = [executable, "-lc", command]
        if shell == "pwsh":
            shell_args = [executable, "-NoLogo", "-NoProfile", "-Command", command]
        returncode, stdout, stderr = await _run_process(shell_args, cwd, float(timeout))
        payload = {
            "exit_code": returncode,
            "stdout": _limit_output(stdout),
            "stderr": _limit_output(stderr),
        }
        return ToolResult("", self.name, json.dumps(payload, ensure_ascii=False), returncode != 0)


async def _run_process(command: Sequence[str], cwd: Path, timeout: float) -> tuple[int, str, str]:
    process = await asyncio.create_subprocess_exec(
        *command,
        cwd=cwd,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(process.communicate(), timeout)
    except TimeoutError:
        process.kill()
        await process.wait()
        raise ValueError(f"Command timed out after {timeout:g} seconds.") from None
    encoding = "utf-8"
    if os.name == "nt":
        encoding = "utf-8"
    return (
        process.returncode or 0,
        stdout_bytes.decode(encoding, errors="replace"),
        stderr_bytes.decode(encoding, errors="replace"),
    )


def _atomic_write(path: Path, content: str) -> None:
    temporary = path.with_name(f".{path.name}.oyster-tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def _string(value: object, name: str, *, allow_empty: bool = False) -> str:
    if not isinstance(value, str) or (not allow_empty and not value):
        suffix = "" if allow_empty else " non-empty"
        raise ValueError(f"{name} must be a{suffix} string")
    return value


def _positive_int(value: object, default: int, name: str) -> int:
    if value is None:
        return default
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise ValueError(f"{name} must be a positive integer")
    return value


def _limit_output(output: str) -> str:
    if len(output) <= MAX_TOOL_OUTPUT_CHARS:
        return output
    half = MAX_TOOL_OUTPUT_CHARS // 2
    omitted = len(output) - (half * 2)
    return f"{output[:half]}\n... {omitted} characters omitted ...\n{output[-half:]}"
