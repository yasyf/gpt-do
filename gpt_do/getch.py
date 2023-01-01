from typing import Callable

import click


def _getch():
    import getch

    def _confirm():
        skip = False

        while ch := getch.getch():
            if skip:
                skip = False
            elif ch.isalnum():
                click.echo(ch)
                return ch
            elif ch.isspace():
                click.echo("")
                return None
            elif ch == "[":
                skip = True

    return _confirm


def _pynput():
    from pynput import keyboard

    class Events(keyboard.Events):
        def __init__(self):
            super(keyboard.Events, self).__init__(
                on_press=self.Press, on_release=self.Release, suppress=True
            )

    try:
        import HIServices

        if not HIServices.AXIsProcessTrusted():
            raise ImportError("pynput is not trusted")
    except Exception:
        pass

    def _confirm():
        with Events() as events:
            for event in events:
                if isinstance(event.key, keyboard.KeyCode):
                    click.echo(event.key.char)
                    return event.key.char
                elif (
                    isinstance(event.key, keyboard.Key)
                    and event.key == keyboard.Key.enter
                ):
                    click.echo("")
                    return None

    return _confirm


def _click():
    return lambda: click.prompt(
        "",
        default="y",
        type=click.Choice(
            ["y", "n"],
            case_sensitive=False,
        ),
        show_choices=False,
        show_default=False,
        prompt_suffix="",
    )


def get_confirm() -> Callable:
    for func in (_pynput, _getch, _click):
        try:
            return func()
        except:
            pass

    raise RuntimeError("No way to get user input!")
