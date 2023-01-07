import click

from gpt_do.cli.common import confirm, standard_args
from gpt_do.wtfers.sql_wtfer import SQLWTFer


@click.group()
def wtf():
    pass


@wtf.command()
@click.argument("request", nargs=-1)
@click.option("--db", type=click.Path(exists=True, resolve_path=True), required=True)
@standard_args
def sql(request: list[str], db: str, debug: bool, yes: bool, model: str):
    model = {"gpt3": "text-davinci-003", "codex": "code-davinci-002"}.get(model, model)
    wtfer = SQLWTFer(db, " ".join(request), debug=debug, model=model)
    for sql in wtfer:
        click.echo(click.style(sql.reason + ".."))
        click.echo(click.style(sql.original_query, fg="bright_black"))
        if not yes and sql.query and not confirm("Execute?"):
            return
        click.echo("")
    click.echo(click.style(wtfer.result.query, fg="green", bold=True))
    if confirm("Execute?"):
        click.echo(click.style(wtfer.execute(), bold=True))


if __name__ == "__main__":
    wtf()
