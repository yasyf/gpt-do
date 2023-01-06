import click

from gpt_do.cli.common import get_doer, run_doer, standard_args


@click.command(context_settings={"auto_envvar_prefix": "GPT_DO"})
@click.argument("request", required=True, nargs=-1)
@standard_args
def do(request: list[str], debug: bool, yes: bool, model: str):
    """Fetches and executes commands in your shell based on the advice of GPT3."""
    doer = get_doer(model)(debug=debug, dangerous=yes)
    run_doer(doer, request, yes)


if __name__ == "__main__":
    do()
