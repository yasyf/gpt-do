import os
from textwrap import dedent

import click
from openai import OpenAI

from gpt_do.doers.doer import Doer


class OpenAIDoer(Doer):
    def __init__(self, model: str = "gpt-5-mini", **kwargs):
        self.model = model
        super().__init__(**kwargs)

    def load_bot(self):
        if not os.getenv("OPENAI_API_KEY"):
            raise click.UsageError(
                dedent(
                    """
                    To use {model}, set an OpenAI API key in OPENAI_API_KEY.
                    You can create one at https://platform.openai.com/api-keys.
                    """
                ).format(model=self.model)
            )
        return OpenAI()

    def prime_convo(self):
        self.dprint(self.prompt)

    def _ask(self, prompt: str) -> str:
        response = self.bot.responses.create(
            model=self.model,
            instructions=self.prompt,
            input=prompt,
            max_output_tokens=512,
            text={
                "format": {
                    "type": "json_schema",
                    "name": "shell_commands",
                    "strict": True,
                    "schema": {
                        "type": "object",
                        "properties": {
                            "commands": {
                                "type": "array",
                                "items": {"type": "string"},
                            },
                            "explanation": {"type": "string"},
                        },
                        "required": ["commands", "explanation"],
                        "additionalProperties": False,
                    },
                }
            },
        )
        self.dprint(response)
        if not response.output_text:
            raise click.ClickException("OpenAI returned an empty response.")
        return response.output_text

    def key_from_query(self, query: str) -> str:
        key = super().key_from_query(query)
        return f"{self.model}:{key}"


# Preserve imports used by existing integrations.
GPT3Doer = OpenAIDoer
