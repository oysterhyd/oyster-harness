# Repository Guidelines

## Project Structure & Module Organization

Application code lives in `src/oyster_harness/`. `cli.py` owns commands and runtime orchestration, `agent.py` implements the agent loop, `context.py` manages bounded conversation context, `input.py` provides the prompt-toolkit input and slash-command menus, `permissions.py` enforces tool policy, `tools.py` contains the tool registry and built-in tools, and `tui.py` renders the Rich terminal UI. Provider interfaces and the OpenCode implementation live in `llm/`. Tests mirror these areas in `tests/`. Record project decisions and milestone status in `docs/development-progress.md`; CI lives in `.github/workflows/ci.yml`.

Do not pre-create speculative subsystems or empty package trees. Add a module when a working capability requires it.

## Build, Test, and Development Commands

- `uv sync --locked --all-groups`: install locked runtime and development dependencies.
- `uv run oyster --help`: inspect available CLI commands.
- `uv run oyster --api-key-file ..\api.txt --workspace . run "hello"`: make a one-shot Hy3 call.
- `uv run oyster --api-key-file ..\api.txt --workspace . chat`: start the interactive coding agent.
- `uv run pytest`: run the complete test suite.
- `uv run ruff check .` and `uv run ruff format --check .`: lint and verify formatting.
- `uv run pyright`: run strict static type checking.
- `uv build`: produce the wheel and source distribution.

## Coding Style & Naming Conventions

Target Python 3.12, use four-space indentation, and keep lines within 100 characters. Ruff handles formatting and linting; Pyright runs in strict mode. Use `snake_case` for modules, functions, and variables, `PascalCase` for classes, and `UPPER_SNAKE_CASE` for constants. Keep provider-specific types inside `llm/` and expose small typed boundaries. Prefer focused functions, explicit async streaming, and the smallest implementation that satisfies a verified behavior.

Keep terminal rendering stateful: dynamic input, tool progress, and the status line must update in place without duplicating scrollback. Preserve Windows ConPTY behavior and the explicit prompt-toolkit application session used when the inherited `TERM` is `dumb`. Context uses each model's advertised window and prefers provider-reported input usage; use the `o200k_base` estimate only as a fallback. User-facing status follows Codex and Claude Code by displaying the remaining context percentage.

## Testing Guidelines

Use pytest. Name files `test_<area>.py` and tests `test_<behavior>()`. Every behavior change needs a test; bug fixes should include a regression case. Unit tests must not call paid or live APIs—use `httpx.MockTransport`. Cover terminal output with prompt-toolkit's in-memory VT100 helpers where possible; manually verify significant TUI changes in a real PTY. When platform-dependent branches change on Windows, also run `uv run pyright --pythonplatform Linux` to match CI analysis. Real Hy3 smoke tests are manual verification and must use a local credential source.

## Commit & Pull Request Guidelines

Follow the existing Conventional Commit style: `feat:`, `chore:`, `docs:`, and `ci:` with imperative summaries. Keep changes narrowly scoped. PRs should explain behavior, list verification commands, link relevant issues, and include terminal output or screenshots for CLI changes.

After completing and verifying project changes, commit and push the current branch automatically unless the user explicitly asks to leave the work uncommitted. Fetch before pushing, stop and report any divergence or conflict, and do not open a pull request unless requested.

## Security & Agent Boundaries

Never commit, print, or log API keys. Use `OPENCODE_API_KEY` or `--api-key-file`; `api.txt` and `.env` are ignored. File tools must remain confined to the configured workspace. Preserve the permission contract: `read-only` rejects mutations, `ask` requires confirmation, and `auto` permits ordinary workspace mutations; commands classified as dangerous remain denied in every mode. Do not advertise models, tools, or protocol features that are not implemented and tested. Update `docs/development-progress.md` whenever a milestone, known limitation, or architectural decision changes.
