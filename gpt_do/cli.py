import click

from gpt_do.getch import get_confirm


def get_doer(model):
    if model == "chatgpt":
        from gpt_do.doers.pywright_doer import PywrightDoer

        return PywrightDoer
    elif model == "gpt3":
        from gpt_do.doers.gpt3_doer import GPT3Doer

        GPT3Doer.model = "text-davinci-003"
        return GPT3Doer
    elif model == "codex":
        from gpt_do.doers.gpt3_doer import GPT3Doer

        GPT3Doer.model = "code-davinci-002"
        return GPT3Doer
    else:
        raise ValueError(f"Unknown model {model}")


_confirm = get_confirm()


def confirm(prompt):
    click.echo(f"{prompt} [Y/n]: ", nl=False)
    if resp := _confirm():
        return resp.lower() == "y"
    return True


@click.command()
@click.argument("request", required=True, nargs=-1)
@click.option("--debug", is_flag=True)
@click.option("--yes", "-y", is_flag=True, help="Do not ask for confirmation")
@click.option(
    "--model",
    default="gpt3",
    type=click.Choice(
        ["gpt3", "codex", "chatgpt"],
        case_sensitive=False,
    ),
)
def do(request: str, debug: bool, yes: bool, model: str):
    """Fetches and executes commands in your shell based on the advice of GPT3."""
    do = get_doer(model)(debug=debug, dangerous=yes)
    response = do.query(" ".join(request))
    click.echo(click.style(response["explanation"], bold=True))
    if not response["commands"]:
        return
    click.echo(click.style("\n".join(response["commands"]), fg="green"))
    if yes or confirm("Execute this command?"):
        click.echo("")
        do.execute(response)


if __name__ == "__main__":
    do()
