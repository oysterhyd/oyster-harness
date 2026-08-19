import asyncio
import os
import sys
from pathlib import Path
from typing import Annotated, Never

import typer
from rich.console import Console

from oyster_harness import __version__
from oyster_harness.agent import AgentSession, AgentSettings, ReasoningEffort
from oyster_harness.config import MissingAPIKeyError, load_api_key
from oyster_harness.input import TerminalPrompt
from oyster_harness.llm.opencode import (
    CHAT_COMPLETION_MODELS,
    DEFAULT_MODEL,
    OpenCodeAPIError,
    OpenCodeProvider,
)
from oyster_harness.permissions import PermissionMode
from oyster_harness.tui import TerminalUI

if os.name == "nt" and sys.stdout.isatty() and os.environ.get("TERM", "").lower() == "dumb":
    os.environ["TERM"] = "xterm-256color"

app = typer.Typer(
    name="oyster",
    help="Grow a coding agent around your workflow.",
    no_args_is_help=False,
    invoke_without_command=True,
)
console = Console()
error_console = Console(stderr=True)

ApiKeyOption = Annotated[
    Path | None,
    typer.Option(
        "--api-key-file",
        help="Read the OpenCode API key from this file.",
        exists=True,
        dir_okay=False,
        readable=True,
    ),
]
WorkspaceOption = Annotated[
    Path,
    typer.Option(
        "--workspace",
        "-w",
        help="Workspace the agent may inspect and modify.",
        exists=True,
        file_okay=False,
        resolve_path=True,
    ),
]


@app.callback()
def root(
    ctx: typer.Context,
    api_key_file: ApiKeyOption = None,
    workspace: WorkspaceOption = Path("."),
) -> None:
    """Run Oyster Harness from the command line."""
    if ctx.invoked_subcommand is None:
        chat(api_key_file=api_key_file, workspace=workspace)


@app.command()
def version() -> None:
    """Show the installed Oyster Harness version."""
    console.print(f"Oyster Harness {__version__}")


@app.command("run")
def run_once(
    prompt: Annotated[str, typer.Argument(help="Task to send to Oyster.")],
    api_key_file: ApiKeyOption = None,
    workspace: WorkspaceOption = Path("."),
    model: Annotated[str, typer.Option("--model", "-m")] = DEFAULT_MODEL,
    reasoning: Annotated[
        ReasoningEffort,
        typer.Option("--reasoning"),
    ] = ReasoningEffort.MEDIUM,
    permissions: Annotated[
        PermissionMode,
        typer.Option("--permissions"),
    ] = PermissionMode.ASK,
) -> None:
    """Run one agent task with tools and bounded context."""
    try:
        session = _create_session(api_key_file, workspace, model, reasoning, permissions)
        ui = TerminalUI(console, workspace)
        ui.show_user(prompt)
        _run_turn(session, ui, prompt)
    except (MissingAPIKeyError, OpenCodeAPIError, ValueError) as exc:
        _exit_with_error(exc)
    except KeyboardInterrupt:
        error_console.print("Request cancelled.")
        raise typer.Exit(130) from None


@app.command()
def chat(
    api_key_file: ApiKeyOption = None,
    workspace: WorkspaceOption = Path("."),
    model: Annotated[str, typer.Option("--model", "-m")] = DEFAULT_MODEL,
    reasoning: Annotated[
        ReasoningEffort,
        typer.Option("--reasoning"),
    ] = ReasoningEffort.MEDIUM,
    permissions: Annotated[
        PermissionMode,
        typer.Option("--permissions"),
    ] = PermissionMode.ASK,
) -> None:
    """Start the interactive Oyster coding agent."""
    try:
        session = _create_session(api_key_file, workspace, model, reasoning, permissions)
    except (MissingAPIKeyError, ValueError) as exc:
        _exit_with_error(exc)

    ui = TerminalUI(console, workspace)
    terminal_prompt = TerminalPrompt(
        console,
        status_provider=lambda: ui.status_plain(
            session.settings,
            session.context_left_percent,
        ),
    )
    ui.show_banner()

    while True:
        try:
            user_input = terminal_prompt.ask()
        except (EOFError, KeyboardInterrupt):
            console.print("\n[dim]The shell closes; the pearl remains.[/]")
            return

        if not user_input:
            continue
        if user_input.startswith("/"):
            if _handle_command(user_input, session, ui, terminal_prompt):
                return
            continue

        ui.show_user(user_input)
        try:
            _run_turn(session, ui, user_input)
        except OpenCodeAPIError as exc:
            ui.show_error(str(exc))
        except KeyboardInterrupt:
            ui.show_error("Request cancelled.")


def _create_session(
    api_key_file: Path | None,
    workspace: Path,
    model: str,
    reasoning: ReasoningEffort,
    permissions: PermissionMode,
) -> AgentSession:
    if model not in CHAT_COMPLETION_MODELS:
        raise ValueError(f"Unsupported Chat Completions model: {model}. Use /models for choices.")
    api_key = load_api_key(api_key_file)
    settings = AgentSettings(
        model=model,
        reasoning_effort=reasoning,
        permission_mode=permissions,
    )
    return AgentSession(OpenCodeProvider(api_key), workspace.resolve(), settings)


def _run_turn(session: AgentSession, ui: TerminalUI, prompt: str) -> None:
    ui.begin_reply(session.settings, session.context_left_percent)
    try:
        result = asyncio.run(session.run(prompt, on_event=ui.handle_event, approve=ui.approve))
    except Exception:
        ui.abort_reply()
        raise
    ui.end_reply(result)


def _handle_command(
    command: str,
    session: AgentSession,
    ui: TerminalUI,
    terminal_prompt: TerminalPrompt,
) -> bool:
    name, _, raw_value = command.partition(" ")
    value = raw_value.strip()
    normalized = name.lower()

    if normalized in {"/exit", "/quit"}:
        console.print("[dim]The shell closes; the pearl remains.[/]")
        return True
    if normalized == "/help":
        ui.show_notice(
            "/model <id>  switch model\n"
            "/models      list supported models\n"
            "/reasoning <none|minimal|low|medium|high|xhigh>\n"
            "/permissions <read-only|ask|auto>\n"
            "/clear       clear conversation context\n"
            "/status      show current runtime settings\n"
            "/exit        leave Oyster"
        )
        return False
    if normalized == "/models":
        ui.show_notice("OpenCode Go · Chat Completions\n\n" + "\n".join(CHAT_COMPLETION_MODELS))
        return False
    if normalized == "/model":
        selected = value or terminal_prompt.choose(
            "Select model",
            tuple(
                (model, f"{model}{'  (current)' if model == session.settings.model else ''}")
                for model in CHAT_COMPLETION_MODELS
            ),
            session.settings.model,
        )
        if selected is None:
            ui.show_notice("Model selection cancelled.", style="yellow")
        elif selected not in CHAT_COMPLETION_MODELS:
            ui.show_notice(
                "Unknown model. Run /models to see supported choices.",
                style="yellow",
            )
        else:
            session.set_model(selected)
            ui.show_notice(f"Model switched to {selected}.")
        return False
    if normalized == "/reasoning":
        selected = value or terminal_prompt.choose(
            "Select reasoning effort",
            tuple(
                (
                    effort.value,
                    f"{effort.value}"
                    f"{'  (current)' if effort is session.settings.reasoning_effort else ''}",
                )
                for effort in ReasoningEffort
            ),
            session.settings.reasoning_effort.value,
        )
        if selected is None:
            ui.show_notice("Reasoning selection cancelled.", style="yellow")
            return False
        try:
            session.set_reasoning_effort(ReasoningEffort(selected))
        except ValueError:
            ui.show_notice(
                "Reasoning must be none, minimal, low, medium, high, or xhigh.",
                style="yellow",
            )
        else:
            ui.show_notice(f"Reasoning effort switched to {selected}.")
        return False
    if normalized in {"/permissions", "/permission"}:
        labels = {
            PermissionMode.READ_ONLY: "read-only  inspect but never modify",
            PermissionMode.ASK: "ask  confirm every mutation",
            PermissionMode.AUTO: "auto  allow non-dangerous mutations",
        }
        selected = value or terminal_prompt.choose(
            "Select agent permissions",
            tuple(
                (
                    mode.value,
                    f"{labels[mode]}"
                    f"{'  (current)' if mode is session.settings.permission_mode else ''}",
                )
                for mode in PermissionMode
            ),
            session.settings.permission_mode.value,
        )
        if selected is None:
            ui.show_notice("Permission selection cancelled.", style="yellow")
            return False
        try:
            session.set_permission_mode(PermissionMode(selected))
        except ValueError:
            ui.show_notice("Permissions must be read-only, ask, or auto.", style="yellow")
        else:
            ui.show_notice(f"Permission mode switched to {selected}.")
        return False
    if normalized == "/clear":
        session.clear()
        ui.show_notice("Conversation context cleared.")
        return False
    if normalized == "/status":
        ui.show_notice("Runtime status is shown below the input box.")
        return False

    ui.show_notice(f"Unknown command: {name}. Run /help for commands.", style="yellow")
    return False


def _exit_with_error(exc: Exception) -> Never:
    error_console.print(f"Error: {exc}", style="bold red")
    raise typer.Exit(1) from exc


def main() -> None:
    """Run the Oyster Harness command-line interface."""
    if os.name == "nt":
        for stream in (sys.stdout, sys.stderr):
            reconfigure = getattr(stream, "reconfigure", None)
            if callable(reconfigure):
                reconfigure(encoding="utf-8")
    app()
