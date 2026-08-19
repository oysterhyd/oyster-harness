import asyncio
from pathlib import Path
from typing import Annotated, Never

import typer
from rich.console import Console

from oyster_harness import __version__
from oyster_harness.config import MissingAPIKeyError, load_api_key
from oyster_harness.conversation import ChatSession
from oyster_harness.llm.opencode import DEFAULT_MODEL, OpenCodeAPIError, OpenCodeProvider

app = typer.Typer(
    name="oyster",
    help="Grow a coding agent from a small, observable core.",
    no_args_is_help=True,
)
console = Console()
error_console = Console(stderr=True)


@app.callback()
def root() -> None:
    """Run Oyster Harness from the command line."""


@app.command()
def version() -> None:
    """Show the installed Oyster Harness version."""
    console.print(f"Oyster Harness {__version__}")


@app.command("run")
def run_once(
    prompt: Annotated[str, typer.Argument(help="Prompt to send to Oyster.")],
    api_key_file: Annotated[
        Path | None,
        typer.Option(
            "--api-key-file",
            help="Read the OpenCode API key from this file.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
) -> None:
    """Send one prompt to OpenCode Go Hy3."""
    try:
        session = _create_session(api_key_file)
        asyncio.run(_render_reply(session, prompt))
    except (MissingAPIKeyError, OpenCodeAPIError) as exc:
        _exit_with_error(exc)
    except KeyboardInterrupt:
        error_console.print("Request cancelled.")
        raise typer.Exit(130) from None


@app.command()
def chat(
    api_key_file: Annotated[
        Path | None,
        typer.Option(
            "--api-key-file",
            help="Read the OpenCode API key from this file.",
            exists=True,
            dir_okay=False,
            readable=True,
        ),
    ] = None,
) -> None:
    """Start a stateful terminal chat with OpenCode Go Hy3."""
    try:
        session = _create_session(api_key_file)
    except MissingAPIKeyError as exc:
        _exit_with_error(exc)

    console.print(f"[bold cyan]Oyster Harness[/] · OpenCode Go / {DEFAULT_MODEL}")
    console.print("Type [bold]/exit[/] to leave.\n")

    while True:
        try:
            user_input = typer.prompt("You").strip()
        except (EOFError, KeyboardInterrupt):
            console.print("\nGoodbye.")
            return

        if user_input.lower() in {"/exit", "/quit"}:
            console.print("Goodbye.")
            return
        if not user_input:
            continue

        try:
            asyncio.run(_render_reply(session, user_input))
        except OpenCodeAPIError as exc:
            _exit_with_error(exc)
        except KeyboardInterrupt:
            error_console.print("\nRequest cancelled.")


def _create_session(api_key_file: Path | None) -> ChatSession:
    api_key = load_api_key(api_key_file)
    return ChatSession(OpenCodeProvider(api_key))


async def _render_reply(session: ChatSession, prompt: str) -> None:
    console.print("[bold cyan]Oyster[/]: ", end="")
    async for chunk in session.reply(prompt):
        console.print(chunk, end="", markup=False, highlight=False)
    console.print()


def _exit_with_error(exc: Exception) -> Never:
    error_console.print(f"Error: {exc}", style="bold red")
    raise typer.Exit(1) from exc


def main() -> None:
    """Run the Oyster Harness command-line interface."""
    app()
