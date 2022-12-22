from chatgpt_wrapper import ChatGPT

from gpt_do.doers.doer import Doer
from gpt_do.vendor.chatgpt_wrapper.chatgpt_wrapper import ChatGPT


class PywrightDoer(Doer):
    def load_bot(self):
        bot = ChatGPT(headless=not self.debug)
        bot.conversation_id = self.state.get("conversation_id")
        bot.parent_message_id = self.state.get("parent_message_id")
        return bot

    def prime_convo(self):
        self.prompt += (
            "\nYou do not need to execute the commands, only print them."
            + " Does that make sense? Respond 'yes' if so."
        )
        self.dprint(self.prompt)

        if self.state:
            return

        response = self.ask(self.prompt).lower()
        self.dprint(response)

        assert "yes" in response

    def _ask(self, prompt: str) -> str:
        return self.bot.ask(prompt)

    def save_state(self):
        self.state["conversation_id"] = self.bot.conversation_id
        self.state["parent_message_id"] = self.bot.parent_message_id
        super().save_state()
