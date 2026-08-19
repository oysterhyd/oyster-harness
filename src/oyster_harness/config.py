import os
from pathlib import Path

API_KEY_ENV = "OPENCODE_API_KEY"


class MissingAPIKeyError(ValueError):
    """Raised when no usable OpenCode API key is configured."""


def load_api_key(api_key_file: Path | None = None) -> str:
    """Load an OpenCode API key without persisting or logging it."""
    if api_key_file is not None:
        try:
            api_key = api_key_file.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise MissingAPIKeyError(f"Cannot read API key file: {api_key_file}") from exc
    else:
        api_key = os.getenv(API_KEY_ENV, "").strip()

    if not api_key:
        raise MissingAPIKeyError(
            f"No OpenCode API key found. Set {API_KEY_ENV} or pass --api-key-file."
        )

    return api_key
