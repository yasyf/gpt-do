import os
import platform
import subprocess
from pathlib import Path
from textwrap import dedent

import click
from revChatGPT.ChatGPT import Chatbot

from gpt_do.doers.chatgpt_doer import ChatGPTDoer


class RevChatGPTDoer(ChatGPTDoer):
    def load_bot(self):
        if not os.getenv("OPENAI_SESSION_TOKEN"):
            raise click.UsageError(
                dedent(
                    """
                    To use ChatGPT, you need to export your session token.
                    Log in here: https://chat.openai.com/api/auth/session.
                    Get the `__Secure-next-auth.session-token` cookie.
                    Expose it in your env as OPENAI_SESSION_TOKEN.
                    """
                )
            )

        driver_path = None
        if platform.system() == "Darwin":
            prefix = subprocess.run(
                ["brew", "--prefix"], stdout=subprocess.PIPE, text=True
            ).stdout
            if (driver := Path(prefix) / "bin" / "chromedriver").exists():
                driver_path = str(driver)

        bot = Chatbot(
            {
                "session_token": os.environ["OPENAI_SESSION_TOKEN"],
                "driver_exec_path": driver_path,
                "verbose": self.debug,
            },
            conversation_id=self.state.get("conversation_id"),
            parent_id=self.state.get("parent_message_id"),
        )
        return bot

    def _ask(self, prompt: str) -> str:
        resp = self.bot.ask(prompt)
        self.state["conversation_id"] = resp.pop("conversation_id")
        self.state["parent_message_id"] = resp.pop("parent_id")
        return resp["message"]
