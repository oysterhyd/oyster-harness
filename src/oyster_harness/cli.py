import typer
from rich.console import Console

from oyster_harness import __version__

app = typer.Typer(
    name="oyster",
    help="Grow a coding agent from a small, observable core.",
    no_args_is_help=True,
)
console = Console()


@app.callback()
def root() -> None:
    """Run Oyster Harness from the command line."""


@app.command()
def version() -> None:
    """Show the installed Oyster Harness version."""
    console.print(f"Oyster Harness {__version__}")


def main() -> None:
    """Run the Oyster Harness command-line interface."""
    app()
