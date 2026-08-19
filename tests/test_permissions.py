from oyster_harness.llm.base import ToolCall
from oyster_harness.permissions import PermissionDecision, PermissionManager, PermissionMode


def _call(name: str, arguments: str = "{}") -> ToolCall:
    return ToolCall("call_1", name, arguments)


def test_ask_mode_allows_reads_and_asks_for_edits() -> None:
    permissions = PermissionManager(PermissionMode.ASK)

    assert permissions.decide(_call("read_file")) is PermissionDecision.ALLOW
    assert permissions.decide(_call("edit_file")) is PermissionDecision.ASK


def test_read_only_mode_denies_mutations_but_allows_safe_shell() -> None:
    permissions = PermissionManager(PermissionMode.READ_ONLY)

    assert permissions.decide(_call("write_file")) is PermissionDecision.DENY
    assert (
        permissions.decide(_call("shell", '{"command":"git status","shell":"pwsh"}'))
        is PermissionDecision.ALLOW
    )


def test_dangerous_commands_are_denied_even_in_auto_mode() -> None:
    permissions = PermissionManager(PermissionMode.AUTO)

    assert (
        permissions.decide(_call("shell", '{"command":"git reset --hard","shell":"bash"}'))
        is PermissionDecision.DENY
    )
