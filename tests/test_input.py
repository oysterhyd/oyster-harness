from io import StringIO
from threading import Thread
from time import sleep

from prompt_toolkit.completion import CompleteEvent
from prompt_toolkit.data_structures import Size
from prompt_toolkit.document import Document
from prompt_toolkit.input.defaults import create_pipe_input
from prompt_toolkit.output import DummyOutput
from prompt_toolkit.output.vt100 import Vt100_Output

from oyster_harness.input import SlashCommandCompleter, create_command_session


def test_slash_opens_command_completions() -> None:
    completer = SlashCommandCompleter()

    completions = list(completer.get_completions(Document("/"), CompleteEvent(text_inserted=True)))

    assert [completion.text for completion in completions[:3]] == [
        "/model",
        "/reasoning",
        "/permissions",
    ]
    assert all(completion.display_meta for completion in completions)


def test_regular_text_does_not_open_command_completions() -> None:
    completions = list(
        SlashCommandCompleter().get_completions(
            Document("explain this"),
            CompleteEvent(text_inserted=True),
        )
    )

    assert completions == []


def test_enter_accepts_the_selected_slash_command() -> None:
    with create_pipe_input() as pipe_input:
        session = create_command_session(input=pipe_input, output=DummyOutput())
        pipe_input.send_text("/\r")

        result = session.prompt()

    assert result == "/model"


def test_submitted_input_is_erased_before_the_user_panel_is_rendered() -> None:
    output_text = StringIO()
    output = Vt100_Output(
        output_text,
        lambda: Size(rows=12, columns=100),
        enable_cpr=False,
    )
    with create_pipe_input() as pipe_input:
        session = create_command_session(input=pipe_input, output=output)

        def submit_after_first_render() -> None:
            sleep(0.05)
            pipe_input.send_text("visible while typing")
            sleep(0.05)
            pipe_input.send_text("\r")

        submitter = Thread(target=submit_after_first_render)
        submitter.start()
        result = session.prompt(
            [("class:prompt", "> ")],
            bottom_toolbar="ONLY ONE STATUSLINE",
        )
        submitter.join()

    rendered = output_text.getvalue()
    final_input = rendered.rfind("visible while typing")

    assert result == "visible while typing"
    assert session.app.erase_when_done is True
    assert "ONLY ONE STATUSLINE" in rendered
    assert "\x1b[J" in rendered[final_input:]
