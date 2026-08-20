import asyncio
from collections.abc import Sequence
from pathlib import Path

from oyster_harness.agent import AgentSession, AgentSettings, ReasoningEffort
from oyster_harness.llm.base import (
    ChatMessage,
    ModelResponse,
    TextCallback,
    ToolCall,
    ToolSchema,
)
from oyster_harness.permissions import PermissionMode


class ScriptedProvider:
    def __init__(self, responses: list[ModelResponse]) -> None:
        self.responses = responses
        self.calls: list[tuple[ChatMessage, ...]] = []
        self.tool_schemas: list[tuple[ToolSchema, ...]] = []

    async def complete(
        self,
        messages: Sequence[ChatMessage],
        *,
        tools: Sequence[ToolSchema] = (),
        model: str,
        reasoning_effort: str,
        on_text: TextCallback | None = None,
    ) -> ModelResponse:
        self.calls.append(tuple(messages))
        self.tool_schemas.append(tuple(tools))
        response = self.responses.pop(0)
        if on_text is not None and response.content:
            on_text(response.content)
        return response


def test_agent_loops_from_tool_call_to_final_answer(tmp_path: Path) -> None:
    (tmp_path / "README.md").write_text("# Pearl\n", encoding="utf-8")
    provider = ScriptedProvider(
        [
            ModelResponse(
                "",
                (ToolCall("call_1", "read_file", '{"path":"README.md"}'),),
                "tool_calls",
            ),
            ModelResponse("The project is Pearl.", (), "stop"),
        ]
    )
    session = AgentSession(provider, tmp_path)

    result = asyncio.run(session.run("What is this project?"))

    assert result.content == "The project is Pearl."
    assert result.iterations == 2
    assert result.tool_calls == 1
    assert {schema.name for schema in provider.tool_schemas[0]} >= {"read_file", "shell"}
    assert provider.calls[1][-1].role == "tool"
    assert "# Pearl" in provider.calls[1][-1].content


def test_read_only_permission_returns_denial_to_model(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    target.write_text("old", encoding="utf-8")
    provider = ScriptedProvider(
        [
            ModelResponse(
                "",
                (
                    ToolCall(
                        "call_1",
                        "edit_file",
                        '{"path":"value.txt","old_text":"old","new_text":"new"}',
                    ),
                ),
                "tool_calls",
            ),
            ModelResponse("I cannot edit in read-only mode.", (), "stop"),
        ]
    )
    settings = AgentSettings(permission_mode=PermissionMode.READ_ONLY)
    session = AgentSession(provider, tmp_path, settings)

    result = asyncio.run(session.run("edit it"))

    assert result.content == "I cannot edit in read-only mode."
    assert target.read_text(encoding="utf-8") == "old"
    assert "Denied by the active permission policy" in provider.calls[1][-1].content


def test_agent_stops_at_iteration_limit(tmp_path: Path) -> None:
    repeated = [
        ModelResponse("", (ToolCall(f"call_{number}", "list_dir", "{}"),), "tool_calls")
        for number in range(2)
    ]
    provider = ScriptedProvider(repeated)
    session = AgentSession(provider, tmp_path, AgentSettings(max_iterations=2))

    result = asyncio.run(session.run("loop"))

    assert result.stop_reason == "max_iterations"
    assert result.tool_calls == 2


def test_ask_permission_can_approve_an_edit(tmp_path: Path) -> None:
    target = tmp_path / "value.txt"
    target.write_text("old", encoding="utf-8")
    provider = ScriptedProvider(
        [
            ModelResponse(
                "",
                (
                    ToolCall(
                        "call_1",
                        "edit_file",
                        '{"path":"value.txt","old_text":"old","new_text":"new"}',
                    ),
                ),
                "tool_calls",
            ),
            ModelResponse("Edited.", (), "stop"),
        ]
    )
    session = AgentSession(provider, tmp_path)

    async def approve(_call: ToolCall) -> bool:
        return True

    result = asyncio.run(session.run("edit it", approve=approve))

    assert result.content == "Edited."
    assert target.read_text(encoding="utf-8") == "new"


def test_system_prompt_tracks_runtime_identity_and_model_switches(tmp_path: Path) -> None:
    provider = ScriptedProvider([ModelResponse("Ready.", (), "stop")])
    session = AgentSession(provider, tmp_path)
    session.set_model("kimi-k3")
    session.set_reasoning_effort(ReasoningEffort.HIGH)
    session.set_permission_mode(PermissionMode.AUTO)

    asyncio.run(session.run("Who are you?"))

    system_prompt = provider.calls[0][0].content
    assert "Product: Oyster Harness" in system_prompt
    assert "Agent name: Oyster" in system_prompt
    assert "Provider: OpenCode Go" in system_prompt
    assert "Active model ID: kimi-k3" in system_prompt
    assert "Reasoning effort: high" in system_prompt
    assert "Permission mode: auto" in system_prompt


def test_hy3_uses_its_model_context_window_and_server_input_usage(tmp_path: Path) -> None:
    provider = ScriptedProvider([ModelResponse("Done.", (), "stop", input_tokens=10_200)])
    session = AgentSession(provider, tmp_path)

    assert session.context_window_tokens == 256_000

    asyncio.run(session.run("Inspect this project."))

    assert session.context_tokens == 10_200
    assert session.context_left_percent == 96


def test_model_switch_updates_automatic_context_window_without_losing_history(
    tmp_path: Path,
) -> None:
    provider = ScriptedProvider([ModelResponse("Ready.", (), "stop")])
    session = AgentSession(provider, tmp_path)
    asyncio.run(session.run("Remember PEARL42."))

    session.set_model("kimi-k3")

    assert session.context_window_tokens == 1_048_576
    assert any("PEARL42" in message.content for message in session.messages)
