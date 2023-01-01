import hashlib
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
from abc import ABC, abstractmethod
from contextlib import contextmanager
from functools import cached_property
from pathlib import Path
from textwrap import dedent
from typing import Any, Literal, Union, overload

import click
import dirtyjson
from retry import retry


class Doer(ABC):
    PROMPT = dedent(
        """
        You are going to translate a natural language description to a series of commands for the {shell} shell.

        You should respond with a JSON object that has the keys "commands" and "explanation'.
        "commands" is an array of strings representing shell commands. If the request would require multiple commands, respond with all the required commands in the array.
        "explanation" is a string which at most one sentence, and cannot contain any other commands. The explanation should help the user understand what the commands are going to do.

        Here is an example:

        {{
            "commands" : ["git log | tail -n 1 > foo.txt", "cat foo.txt"],
            "explanation" : "These commands will...",
        }}

        Do not respond with anything other than this JSON. Your response should be valid JSON. Do not include any notes.
        Do not rename the keys "commands" or "explanation".
        {dangerous}

        Environment: {uname}
        Working Directory: {cwd}
        Shell History:
        {history}

    """
    )

    def __init__(self, debug: bool = False, dangerous: bool = False) -> None:
        self.shell_path = os.getenv("SHELL", "/usr/bin/bash")
        self.shell = os.path.split(self.shell_path)[-1]
        self.bin = click.get_current_context().command_path

        self.dangerous = dangerous
        self.debug = debug
        self.state = self.load_state()

        self.bot = self.load_bot()

        self.prime_convo()

    def history(self):
        result = subprocess.run(
            f"{self.shell_path} -lc 'history | head -n 10'",
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            shell=True,
        )
        for line in reversed([l.strip() for l in result.stdout.split("\n")][1:]):
            if line.startswith(self.bin):
                ctx = click.Context(click.get_current_context().command)
                opts, _, _ = ctx.command.make_parser(ctx).parse_args(
                    line.removeprefix('"').removesuffix('"').split(" ")[1:]
                )
                query = " ".join(opts.get("request", tuple()))
                yield f"# {query}"
                if cached := self.check_cache(query):
                    yield from (f"$ {c}" for c in cached["commands"] if c)
                if (log := self.log_path(query)).exists():
                    yield from (
                        f"> {click.unstyle(c)}"
                        for c in log.read_text().split("\n")
                        if c
                    )
            elif line.startswith("export"):
                continue
            elif line:
                yield f"$ {line}"

    @cached_property
    def prompt(self):
        return self.PROMPT.format(
            shell=self.shell,
            uname=repr(list(os.uname())),
            dangerous="If you are suggesting a destructive command, ensure it is wrapped in a confirmation."
            if self.dangerous
            else "",
            history="\n".join(self.history()),
            cwd=os.getcwd(),
        )

    def dprint(self, *args):
        if self.debug:
            print(*args, file=sys.stderr)

    @abstractmethod
    def load_bot(self) -> Any:
        ...

    @abstractmethod
    def _ask(self, prompt: str) -> str:
        ...

    @abstractmethod
    def prime_convo(self):
        ...

    @cached_property
    def cache_path(self) -> Path:
        path = Path(os.getenv("XDG_CACHE_HOME", "~/.cache")).expanduser() / "do"
        (path / "logs").mkdir(parents=True, exist_ok=True)
        return path

    @property
    def state_path(self) -> Path:
        return self.cache_path / "state.json"

    def log_path(self, query) -> Path:
        key = self.key_from_query(query)
        return self.cache_path / "logs" / f"{key}.txt"

    def key_from_query(self, query: str) -> str:
        return hashlib.md5(query.encode("utf-8")).hexdigest()

    def load_state(self):
        if not self.state_path.exists():
            return {}
        else:
            return json.load(self.state_path.open())

    def save_state(self):
        json.dump(self.state, self.state_path.open("w"))

    @overload
    def ask(self, prompt: str) -> str:
        ...

    @overload
    def ask(self, prompt: str, is_json: Literal[True]) -> dict:
        ...

    def ask(self, prompt: str, is_json: bool = False) -> Union[str, dict]:
        resp = self._ask(prompt)
        if not is_json:
            return resp

        try:
            resp = dirtyjson.loads(resp)
        except Exception:
            self.dprint(resp)
            raise click.UsageError("GPT returned an invalid response. Try again?")

        if not isinstance(resp, dict) or any(
            k not in resp for k in ("commands", "explanation")
        ):
            self.dprint(resp)
            raise click.UsageError("GPT returned an invalid response. Try again?")

        return resp

    def check_cache(self, query) -> Union[dict, None]:
        return self.state.get("cache", {}).get(self.key_from_query(query))

    def update_cache(self, query, value):
        cache = self.state["cache"] = self.state.get("cache", {})
        cache[self.key_from_query(query)] = value

    @retry(tries=3, delay=0.5)
    def query(self, query) -> dict:
        if not (resp := self.check_cache(query)):
            resp = self.ask(query, is_json=True)
            self.update_cache(query, resp)
            self.save_state()

        resp["query"] = query
        return resp

    @contextmanager
    def executable(self):
        f = tempfile.NamedTemporaryFile(mode="w+t", suffix=f".{self.shell}")
        f.write(f"#!{self.shell_path} -l\n")
        yield f
        f.flush()
        os.chmod(f.name, os.stat(f.name).st_mode | stat.S_IEXEC)

    def execute(self, resp: dict) -> None:
        with self.executable() as f:
            f.write("\n".join(resp["commands"]))

        if script_path := shutil.which("script"):
            with self.executable() as f2:
                f2.write(
                    f"{script_path} -q -t0 {self.log_path(resp['query'])} {f.name}"
                )
            os.execl(self.shell_path, "-c", f2.name)
        else:
            os.execl(self.shell_path, "-lc", f.name)
