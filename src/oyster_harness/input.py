import sys
from collections.abc import Callable, Iterable, Sequence
from dataclasses import dataclass

from prompt_toolkit import PromptSession
from prompt_toolkit.application import Application
from prompt_toolkit.application.current import get_app, get_app_session
from prompt_toolkit.completion import CompleteEvent, Completer, Completion
from prompt_toolkit.document import Document
from prompt_toolkit.filters import Condition
from prompt_toolkit.history import InMemoryHistory
from prompt_toolkit.input import Input
from prompt_toolkit.key_binding import KeyBindings
from prompt_toolkit.key_binding.key_processor import KeyPressEvent
from prompt_toolkit.output import Output
from prompt_toolkit.shortcuts import CompleteStyle
from prompt_toolkit.shortcuts.choice_input import ChoiceInput
from prompt_toolkit.styles import Style
from rich.console import Console
from rich.prompt import Prompt


@dataclass(frozen=True, slots=True)
class CommandItem:
    value: str
    description: str


COMMAND_ITEMS = (
    CommandItem("/model", "switch the active model"),
    CommandItem("/reasoning", "set reasoning effort"),
    CommandItem("/permissions", "set agent permissions"),
    CommandItem("/models", "list supported models"),
    CommandItem("/clear", "clear conversation context"),
    CommandItem("/status", "show runtime settings"),
    CommandItem("/help", "show command help"),
    CommandItem("/exit", "leave Oyster"),
)

_MIN_RENDER_ROWS = 2

_PROMPT_STYLE = Style.from_dict(
    {
        "prompt": "bold #67e8f9",
        "bottom-toolbar": "bg:#0f172a #94a3b8 noreverse",
        "completion-menu.completion": "bg:#0f172a #cbd5e1",
        "completion-menu.completion.current": "bg:#4f46e5 #ffffff bold",
        "completion-menu.meta.completion": "bg:#0f172a #94a3b8",
        "completion-menu.meta.completion.current": "bg:#4f46e5 #e0e7ff",
        "frame.border": "#475569",
        "input-selection": "#cbd5e1",
        "selected-option": "bold #67e8f9",
        "number": "#64748b",
        "bottom-toolbar.text": "bg:#0f172a #94a3b8 noreverse",
    }
)


@Condition
def _entering_slash_command() -> bool:
    return get_app().current_buffer.text.startswith("/")


class SlashCommandCompleter(Completer):
    """Show commands only while the user is entering a slash command."""

    def get_completions(
        self,
        document: Document,
        complete_event: CompleteEvent,
    ) -> Iterable[Completion]:
        del complete_event
        text = document.text_before_cursor
        if not text.startswith("/") or " " in text:
            return
        for item in COMMAND_ITEMS:
            if item.value.startswith(text.lower()):
                yield Completion(
                    item.value,
                    start_position=-len(text),
                    display=item.value,
                    display_meta=item.description,
                )


class TerminalPrompt:
    """Interactive text prompt with a slash command palette and config chooser."""

    def __init__(
        self,
        console: Console,
        status_provider: Callable[[], str] | None = None,
    ) -> None:
        self._console = console
        self._status_provider = status_provider or (lambda: "")
        self._session = (
            create_command_session()
            if sys.stdin.isatty() and sys.stdout.isatty() and console.is_terminal
            else None
        )

    def ask(self) -> str:
        if self._session is None:
            return Prompt.ask("[bold #67e8f9]❯[/]", console=self._console).strip()
        return self._session.prompt(
            [("class:prompt", "❯ ")],
            bottom_toolbar=self._input_toolbar,
        ).strip()

    def choose(
        self,
        title: str,
        options: Sequence[tuple[str, str]],
        current: str,
    ) -> str | None:
        if self._session is None:
            return None
        try:
            selector = ChoiceInput[str](
                message=title,
                options=options,
                default=current,
                style=_PROMPT_STYLE,
                symbol="●",
                bottom_toolbar=self._choice_toolbar,
                show_frame=True,
            )
            application = selector._create_application()  # pyright: ignore[reportPrivateUsage]
            application.erase_when_done = True
            application.before_render += _keep_transient_area_compact
            return application.run()
        except KeyboardInterrupt:
            return None

    def _input_toolbar(self) -> str:
        return f" {self._status_provider()}"

    def _choice_toolbar(self) -> str:
        return f" {self._status_provider()}"


def create_command_session(
    *,
    input: Input | None = None,
    output: Output | None = None,
) -> PromptSession[str]:
    app_session = get_app_session()
    session = PromptSession[str](
        history=InMemoryHistory(),
        completer=SlashCommandCompleter(),
        complete_while_typing=_entering_slash_command,
        enable_history_search=False,
        complete_style=CompleteStyle.COLUMN,
        reserve_space_for_menu=len(COMMAND_ITEMS) + 1,
        key_bindings=_command_key_bindings(),
        style=_PROMPT_STYLE,
        input=input or app_session.input,
        output=output or app_session.output,
        erase_when_done=True,
        show_frame=True,
    )
    session.app.before_render += _keep_transient_area_compact
    return session


def _keep_transient_area_compact(application: Application[str]) -> None:
    """Keep input and status together instead of filling all remaining terminal rows."""
    application.renderer._min_available_height = (  # pyright: ignore[reportPrivateUsage]
        _MIN_RENDER_ROWS
    )


def _command_key_bindings() -> KeyBindings:
    bindings = KeyBindings()

    @bindings.add("enter", eager=True)
    def _(event: KeyPressEvent) -> None:
        buffer = event.current_buffer
        completion_state = buffer.complete_state
        if completion_state is not None and completion_state.completions:
            completion = completion_state.current_completion or completion_state.completions[0]
            buffer.apply_completion(completion)
        elif buffer.text.startswith("/") and " " not in buffer.text:
            match = next(
                (
                    item.value
                    for item in COMMAND_ITEMS
                    if item.value.startswith(buffer.text.lower())
                ),
                None,
            )
            if match is not None:
                buffer.text = match
                buffer.cursor_position = len(match)
        buffer.validate_and_handle()

    return bindings
