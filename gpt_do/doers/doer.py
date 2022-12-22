import json
import os
import sys
import tempfile
from abc import ABC, abstractmethod
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

        Here is some information about the environment: {uname}

        You should respond with the following JSON object.

        {{
            "commands" : ["ls", "cat", ...],
            "explanation" : "These commands will...",
        }}

        Do not respond with anything other than this JSON. Your response should be valid JSON. Do not include any notes.

        The explanation must be at most one sentence, and cannot contain any other commands.
        The explanation should help the user understand what the commands are going to do.
        If the request would require multiple commands, respond with all the required commands in the array.
    """
    )

    def __init__(self, debug: bool = False) -> None:
        self.shell_path = os.getenv("SHELL", "/usr/bin/bash")
        self.shell = os.path.split(self.shell_path)[-1]
        self.prompt = self.PROMPT.format(shell=self.shell, uname=repr(list(os.uname())))

        self.debug = debug
        self.state = self.load_state()

        self.bot = self.load_bot()

        self.prime_convo()

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
    def state_path(self) -> Path:
        path = Path(os.getenv("XDG_CACHE_HOME", "~/.cache")).expanduser() / "do"
        path.mkdir(parents=True, exist_ok=True)
        return path / "state.json"

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

        return resp

    def check_cache(self, key):
        return self.state.get("cache", {}).get(key)

    def update_cache(self, key, value):
        cache = self.state["cache"] = self.state.get("cache", {})
        cache[key] = value

    @retry(tries=3, delay=0.5)
    def query(self, query) -> dict:
        if cached := self.check_cache(query):
            return cached

        resp = self.ask(query, is_json=True)
        self.update_cache(query, resp)
        self.save_state()
        return resp

    def execute(self, commands: list) -> None:
        f = tempfile.NamedTemporaryFile(suffix=f".{self.shell}")
        f.write("\n".join(commands).encode("utf-8"))
        f.flush()
        os.execl(self.shell_path, "-c", f.name)
