import re
import shutil

import click

from gpt_do.cli.common import get_doer, run_doer, standard_args
from gpt_do.cli.do import do


@click.command(context_settings={"auto_envvar_prefix": "GPT_DO"})
@standard_args
@click.option("--bin", required=True, default="do")
@click.option("--code", type=int, required=True, default=-1)
def derr(debug: bool, yes: bool, model: str, bin: str, code: int):
    """Retries a failed command."""
    with click.Context(do, info_name=bin):
        doer = get_doer(model)(debug=debug, dangerous=yes)
        query, commands, error = doer.last_command()

    if not query:
        raise click.UsageError("Could not find last command.")

    bins = [c.split(" ")[0] for c in commands]
    if missing := next(filter(lambda x: not shutil.which(x), set(bins)), None):
        message = f"That failed because `{missing}` could not be found."
        request = f"`{missing}` is not installed. Try without using `{missing}`."
    elif error and (match := re.search(r"No module named '(.*)'", error)):
        module = match.group(1)
        message = f"That failed because `{module}` could not be found."
    elif error:
        message = f"That failed with error '{error}' ({code})."
        request = f"That failed with error code {code}. Try another way."
    else:
        message = f"That failed with error code {code}."
        request = f"That failed with error code {code}. Try without using `{bins[0]}`"

    if doer.log_path(query).open("r+t").readlines()[-1].strip() == message:
        raise click.ClickException(click.style("GPT is in a loop!", fg="red"))

    click.echo(click.style(message, fg="yellow"))
    click.echo(click.style(f"do {request}", fg="green"))
    doer.log_path(query).open("a+t").write(f"{message}\n")

    run_doer(doer, [request], yes)


if __name__ == "__main__":
    derr()
