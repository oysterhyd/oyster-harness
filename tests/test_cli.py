from typer.testing import CliRunner

from oyster_harness import __version__
from oyster_harness.cli import app

runner = CliRunner()


def test_help_describes_oyster() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "Grow a coding agent" in result.stdout


def test_version_reports_package_version() -> None:
    result = runner.invoke(app, ["version"])

    assert result.exit_code == 0
    assert f"Oyster Harness {__version__}" in result.stdout
