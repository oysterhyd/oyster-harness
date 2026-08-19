from pathlib import Path

import pytest

from oyster_harness.config import API_KEY_ENV, MissingAPIKeyError, load_api_key


def test_load_api_key_from_explicit_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "environment-key")
    key_file = tmp_path / "api.txt"
    key_file.write_text("  file-key\n", encoding="utf-8")

    assert load_api_key(key_file) == "file-key"


def test_load_api_key_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(API_KEY_ENV, "  environment-key  ")

    assert load_api_key() == "environment-key"


def test_missing_api_key_has_actionable_message(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(API_KEY_ENV, raising=False)

    with pytest.raises(MissingAPIKeyError, match=API_KEY_ENV):
        load_api_key()
