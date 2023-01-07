import shutil
from textwrap import dedent
from typing import cast

import click
import dirtyjson

from gpt_do.doers.doer import Doer


class ChatGPTDoer(Doer):
    PROMPT = dedent(
        """
        I need your help to accomplish some things at my shell. I will tell them to you, and you will write a program.

        You can write programs in either language: python or {shell} shell.

        The program should be idempotent. For example, instead of using `mkdir`, use `mkdir -p`.
        {dangerous}

        You should also include an explanation with each program, to help me understand what's happening. The explanation should be concise, and no more than 2 sentences.

        The format I would like is as follows. Do not include a preamble.
        ---
        {{"lang": "python or {shell}", "explanation": "explanation here"}}

        ```
        CODE
        ```
        ---

        Here's some context about my environment: {uname}
        My current working directory is: {cwd}
        Here is some recent shell history:
        {history}

        Do you understand the instructions?
    """
    )

    def prime_convo(self):
        state = self.state.copy()
        state.pop("cache")

        if any(state.values()):
            self.dprint("Using existing state: {}".format(state))
            return

        self.dprint(self.prompt)
        response = self._ask(self.prompt).lower()
        self.dprint(response)

        assert "yes" in response

    def ask(self, prompt: str, **kwargs) -> str:
        kwargs.pop("is_json", None)
        raw = super().ask(prompt, **kwargs)
        json_start, json_end = raw.find("{"), raw.find("}")
        json = raw[json_start : json_end + 1]

        try:
            resp = dirtyjson.loads(json)
        except Exception:
            self.dprint(raw)
            raise click.UsageError("GPT returned an invalid response. Try again?")

        if not isinstance(resp, dict) or any(
            k not in resp for k in ("lang", "explanation")
        ):
            self.dprint(raw)
            raise click.UsageError("GPT returned an invalid response. Try again?")

        code_start, code_end = raw.find("\n", raw.find("```", json_end)), raw.rfind(
            "```", json_end
        )
        resp["commands"] = [raw[code_start + 1 : code_end]]

        return resp

    def execute(self, resp: dict) -> None:
        if resp["lang"] == "python" and (bin := shutil.which("python")):
            exec_bin = [cast(str, bin)]
        else:
            exec_bin = []

        # Pip install requirements if missing
        with self.executable(exec_bin) as f:
            f.write(resp["commands"][0])
        return self._execute(f, resp)
