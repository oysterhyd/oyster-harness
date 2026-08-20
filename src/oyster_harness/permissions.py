import json
import re
from enum import StrEnum
from typing import cast

from oyster_harness.llm.base import ToolCall


class PermissionMode(StrEnum):
    """How much autonomy the current agent session has."""

    READ_ONLY = "read-only"
    ASK = "ask"
    AUTO = "auto"


class PermissionDecision(StrEnum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


_READ_TOOLS = frozenset({"list_dir", "read_file", "grep"})
_WRITE_TOOLS = frozenset({"edit_file", "write_file"})
_DANGEROUS_COMMANDS = (
    re.compile(r"\bsudo\b", re.IGNORECASE),
    re.compile(r"\brm\s+-[^\r\n]*r[^\r\n]*f\s+[/~]?(?:\s|$)", re.IGNORECASE),
    re.compile(r"\bgit\s+reset\s+--hard\b", re.IGNORECASE),
    re.compile(r"\bgit\s+push\b[^\r\n]*(?:--force|-f)\b", re.IGNORECASE),
    re.compile(r"\b(?:shutdown|reboot)\b", re.IGNORECASE),
    re.compile(r"(?<![-\w])format(?:\.com)?(?=\s|$)", re.IGNORECASE),
    re.compile(r"\bFormat-Volume\b", re.IGNORECASE),
    re.compile(r"\bRemove-Item\b[^\r\n]*\b-Recurse\b", re.IGNORECASE),
)
_READ_ONLY_COMMANDS = (
    re.compile(r"^(?:pwd|ls|dir|cat|rg)(?:\s|$)", re.IGNORECASE),
    re.compile(r"^Get-(?:Location|ChildItem|Content)(?:\s|$)", re.IGNORECASE),
    re.compile(r"^git\s+(?:status|diff|log|show)(?:\s|$)", re.IGNORECASE),
    re.compile(r"^(?:pytest|pyright)(?:\s|$)", re.IGNORECASE),
    re.compile(r"^ruff\s+(?:check|format\s+--check)(?:\s|$)", re.IGNORECASE),
    re.compile(
        r"^uv\s+run\s+(?:pytest|pyright|ruff\s+check|ruff\s+format\s+--check)(?:\s|$)",
        re.IGNORECASE,
    ),
    re.compile(r"^python\s+-m\s+pytest(?:\s|$)", re.IGNORECASE),
)


class PermissionManager:
    """Apply non-prompt security policy before a tool reaches the executor."""

    def __init__(self, mode: PermissionMode = PermissionMode.ASK) -> None:
        self.mode = mode

    def decide(self, call: ToolCall) -> PermissionDecision:
        if call.name in _READ_TOOLS:
            return PermissionDecision.ALLOW

        if call.name == "shell":
            command = _shell_command(call.arguments)
            if command is None or _is_dangerous(command):
                return PermissionDecision.DENY
            if _is_read_only(command):
                return PermissionDecision.ALLOW
            return self._mutation_decision()

        if call.name in _WRITE_TOOLS:
            return self._mutation_decision()

        return PermissionDecision.DENY

    def _mutation_decision(self) -> PermissionDecision:
        if self.mode is PermissionMode.AUTO:
            return PermissionDecision.ALLOW
        if self.mode is PermissionMode.ASK:
            return PermissionDecision.ASK
        return PermissionDecision.DENY


def _shell_command(arguments: str) -> str | None:
    try:
        parsed_object = json.loads(arguments)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed_object, dict):
        return None
    parsed = cast(dict[str, object], parsed_object)
    command = parsed.get("command")
    return command.strip() if isinstance(command, str) else None


def _is_dangerous(command: str) -> bool:
    return any(pattern.search(command) for pattern in _DANGEROUS_COMMANDS)


def _is_read_only(command: str) -> bool:
    if any(token in command for token in (";", "&&", "||", "|", ">", "<", "`", "$(`")):
        return False
    return any(pattern.search(command.strip()) for pattern in _READ_ONLY_COMMANDS)
