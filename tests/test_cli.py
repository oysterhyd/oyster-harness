from pathlib import Path

import pytest
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


def test_help_lists_model_commands() -> None:
    result = runner.invoke(app, ["--help"])

    assert result.exit_code == 0
    assert "chat" in result.stdout
    assert "run" in result.stdout


def test_run_requires_an_api_key(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("OPENCODE_API_KEY", raising=False)

    result = runner.invoke(app, ["run", "hello"])

    assert result.exit_code == 1
    assert "No OpenCode API key found" in result.stderr
