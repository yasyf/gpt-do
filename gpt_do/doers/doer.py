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
from functools import cached_property, lru_cache
from pathlib import Path
from textwrap import dedent
from typing import Any, Literal, Optional, Union, overload

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
        The commands should be idempotent. For example, instead of using `mkdir`, use `mkdir -p`.
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
        self._errored = False

        self.prime_convo()

    @cached_property
    def _session_id(self):
        return os.getenv("TERM_SESSION_ID", str(os.getppid()))

    @cached_property
    def _history(self):
        return [
            l.strip()
            for l in reversed(
                subprocess.run(
                    {
                        "fish": "history | head -n 10",
                        "bash": "cat ~/.bash_history | tail -n 10",
                        "zsh": "cat ~/.zsh_history | tail -n 10",
                    }.get(self.shell, "history | head -n 10 | cut -c 8-"),
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL,
                    text=True,
                    shell=True,
                ).stdout.split("\n")
            )
        ]

    @staticmethod
    def _clean_line(line):
        return line.removeprefix('"').removesuffix('"').split(" ")[1:]

    @lru_cache
    def _extract_query(self, line):
        ctx = click.Context(click.get_current_context().command)
        opts, _, _ = ctx.command.make_parser(ctx).parse_args(self._clean_line(line))
        return " ".join(opts.get("request", tuple()))

    @lru_cache
    def _extract_code(self, line):
        parser = click.OptionParser()
        parser.add_option(
            None,
            ["--code"],
            "code",
        )
        opts, _, _ = parser.parse_args(self._clean_line(line))
        return opts.get("code", "-1")

    def _history_sessions(self):
        for i, l in enumerate(self._history):
            if l.startswith(self.bin) and (
                cached := self.check_cache(self._extract_query(l))
            ):
                yield (i, cached.get("session") or self._session_id)

    @cached_property
    def history_sessions(self) -> list[tuple[int, str]]:
        return list(self._history_sessions())

    @property
    def has_dynamic_history(self) -> bool:
        return bool(self.history_sessions[1:]) and not self._errored

    @cached_property
    def _history_index(self) -> int:
        if self.has_dynamic_history:
            try:
                return max(
                    [
                        t[0]
                        for t in self.history_sessions[1:]
                        if t[1] != self._session_id
                    ]
                )
            except ValueError:
                return 0
        else:
            return 0

    @cached_property
    def _redo_index(self) -> Optional[int]:
        try:
            return max(
                [t[0] for t in self.history_sessions if t[1] == self._session_id]
            )
        except ValueError:
            return None

    def last_command(self) -> tuple[Optional[str], list[str], Optional[str]]:
        query, commands, error = None, [], None

        if not self._redo_index:
            return query, commands, error

        line = self._history[self._redo_index]
        query = self._extract_query(line)

        if cached := self.check_cache(query):
            commands = cached["commands"]
        if log := self.log_path(query):
            error = next(
                (l for l in log.read_text().split("\n") if l.strip()),
                None,
            )

        return query, commands, error

    def history(self):
        for line in self._history[self._history_index + 1 :]:
            if line.startswith(self.bin):
                query = self._extract_query(line)
                yield f"# {query}"
                if cached := self.check_cache(query):
                    yield from (f"$ {c}" for c in cached["commands"] if c)
                if (log := self.log_path(query)).exists():
                    yield from (
                        f"> {click.unstyle(c)}"
                        for c in log.read_text().split("\n")
                        if c
                    )
            elif line.startswith("export") or line.startswith("derr"):
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
        value["session"] = self._session_id

        cache = self.state["cache"] = self.state.get("cache", {})
        cache[self.key_from_query(query)] = value

    @retry(tries=3, delay=0.5)
    def _query(self, query) -> dict:
        if self.has_dynamic_history or not (resp := self.check_cache(query)):
            resp = self.ask(query, is_json=True)
            self.update_cache(query, resp)
            self.save_state()

        resp["query"] = query
        return resp

    def query(self, query) -> dict:
        if not self._errored:
            try:
                return self._query(query)
            except:
                self._errored = True

        try:
            return self._query(query)
        except:
            raise click.ClickException("OpenAI is not currently accessible.")

    @contextmanager
    def executable(self):
        f = tempfile.NamedTemporaryFile(
            mode="w+t", suffix=f".{self.shell}", delete=False
        )
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
                    "trap '"
                    + (
                        "set DO_STATUS $status"
                        if self.shell == "fish"
                        else "DO_STATUS=$?"
                    )
                    + "; "
                    + {
                        "fish": "history save",
                        "bash": 'shopt -s histappend; PROMPT_COMMAND="history -a;$PROMPT_COMMAND"',
                        "zsh": "setopt inc_append_history",
                    }.get(self.shell, "")
                    + f"; test $DO_STATUS -ne 0 && derr --bin {self.bin} --code $DO_STATUS' "
                    + (" EXIT\n" if self.shell == "fish" else "ERR\n")
                )
                f2.write(
                    f"{script_path} -q -t0 {self.log_path(resp['query'])} {f.name}"
                )
            os.execl(self.shell_path, "-c", f2.name)
        else:
            os.execl(self.shell_path, "-lc", f.name)
