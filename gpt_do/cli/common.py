import os
from functools import wraps
from typing import TYPE_CHECKING

import click

from gpt_do.getch import get_confirm

if TYPE_CHECKING:
    from gpt_do.doers.doer import Doer

_confirm = get_confirm()


def confirm(prompt):
    click.echo(f"{prompt} [Y/n]: ", nl=False)
    if resp := _confirm():
        return resp.lower() == "y"
    return True


def standard_args(fn):
    @click.option("--debug/--no-debug", is_flag=True)
    @click.option(
        "--yes/--no", "-y/-n", is_flag=True, help="Do not ask for confirmation"
    )
    @click.option(
        "--model",
        default="gpt-5-mini",
        show_default=True,
        help="OpenAI model ID to use.",
    )
    @wraps(fn)
    def wrapped(*args, **kwargs):
        for param in ("debug", "yes", "model"):
            os.environ[f"GPT_DO_{param.upper()}"] = str(
                click.get_current_context().params[param]
            )
        return fn(*args, **kwargs)

    return wrapped


def get_doer(model, **kwargs):
    from gpt_do.doers.openai_doer import OpenAIDoer

    return OpenAIDoer(model=model, **kwargs)


def run_doer(doer: "Doer", request: list[str], yes: bool):
    response = doer.query(" ".join(request))
    click.echo(click.style(response["explanation"], bold=True))
    if not response["commands"]:
        return
    click.echo(click.style("\n".join(response["commands"]), fg="green"))
    if yes or confirm("Execute this command?"):
        click.echo("")
        doer.execute(response)
