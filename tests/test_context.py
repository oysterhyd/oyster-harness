from oyster_harness.context import ContextManager, count_text_tokens
from oyster_harness.llm.base import ChatMessage
from oyster_harness.tools import ToolResult


def test_text_count_uses_tokens_instead_of_characters() -> None:
    text = "Oyster Harness 你好"

    assert count_text_tokens(text) == 5
    assert count_text_tokens(text) != len(text)


def test_context_compacts_old_turns_and_keeps_working_memory() -> None:
    context = ContextManager(max_tokens=800, max_tool_result_tokens=100)
    context.record(
        ToolResult("call_1", "edit_file", "Updated src/app.py", modified_path="src/app.py")
    )
    messages = [ChatMessage("system", "system")]
    for number in range(8):
        messages.extend(
            (
                ChatMessage("user", f"turn {number} " + "u" * 500),
                ChatMessage("assistant", "answer " * 200),
            )
        )

    built = context.build(tuple(messages))

    assert context.estimate(built) <= 800
    assert any("Earlier conversation was compacted" in message.content for message in built)
    assert any("src/app.py" in message.content for message in built)
    assert built[-2].content.startswith("turn 7")


def test_context_trims_large_tool_results() -> None:
    context = ContextManager(max_tokens=800, max_tool_result_tokens=100)
    messages = (
        ChatMessage("system", "system"),
        ChatMessage("user", "inspect"),
        ChatMessage("tool", "tool output " * 1_000, tool_call_id="call_1"),
    )

    built = context.build(messages)

    assert count_text_tokens(built[-1].content) <= 100
    assert "compacted" in built[-1].content


def test_context_keeps_latest_oversized_user_turn_within_budget() -> None:
    context = ContextManager(max_tokens=800)
    messages = (
        ChatMessage("system", "system"),
        ChatMessage("user", "old turn"),
        ChatMessage("assistant", "old answer"),
        ChatMessage("user", "LATEST " + "large request " * 2_000),
    )

    built = context.build(messages)

    assert context.estimate(built) <= 800
    assert built[-1].content.startswith("LATEST")


def test_context_reports_whole_percentage_remaining() -> None:
    context = ContextManager(max_tokens=800)
    small = (ChatMessage("system", "system"),)
    large = (
        ChatMessage("system", "system"),
        ChatMessage("user", "request " * 2_000),
    )

    assert context.remaining_percentage(small) > context.remaining_percentage(large)
    assert 0 <= context.remaining_percentage(large) <= 100
