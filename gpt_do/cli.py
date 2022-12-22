import click

from gpt_do.doers.gpt3_doer import GPT3Doer
from gpt_do.doers.pywright_doer import PywrightDoer


def get_doer(model):
    if model == "chatgpt":
        return PywrightDoer
    elif model == "gpt3":
        GPT3Doer.model = "text-davinci-003"
        return GPT3Doer
    elif model == "codex":
        GPT3Doer.model = "code-davinci-002"
        return GPT3Doer
    else:
        raise ValueError(f"Unknown model {model}")


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
    do = get_doer(model)(debug=debug)
    response = do.query(" ".join(request))
    click.echo(click.style(response["explanation"], bold=True))
    click.echo(click.style("\n".join(response["commands"]), fg="green"))
    if yes or click.confirm("Do you want to continue?"):
        do.execute(response["commands"])


if __name__ == "__main__":
    do()
