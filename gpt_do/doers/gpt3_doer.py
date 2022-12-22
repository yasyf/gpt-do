import os
from textwrap import dedent

import click
import openai

from gpt_do.doers.doer import Doer


class GPT3Doer(Doer):
    model = "text-davinci-003"

    def load_bot(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise click.UsageError(
                dedent(
                    """
                    To use {model}, you need to set an API key for OpenAI.
                    You can get one here: https://beta.openai.com/account/api-keys.
                    Make sure to expose it in your env as OPENAI_API_KEY.
                    """
                ).format(model=self.model)
            )

    def prime_convo(self):
        self.dprint(self.prompt)

    def _ask(self, prompt: str) -> str:
        contents = openai.Completion.create(
            engine=self.__class__.model,
            prompt=f"{self.prompt}\nRequest: {prompt}\n{{",
            stop="}\n",
            temperature=0,
            max_tokens=256,
        )
        self.dprint(contents)
        return "{" + contents.choices[0]["text"] + "}"

    def check_cache(self, key):
        return self.state.get("cache", {}).get(f"{self.model}:{key}")

    def update_cache(self, key, value):
        cache = self.state["cache"] = self.state.get("cache", {})
        cache[f"{self.model}:{key}"] = value
