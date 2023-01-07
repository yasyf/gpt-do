from gpt_do.doers.chatgpt_doer import ChatGPTDoer
from gpt_do.vendor.chatgpt_wrapper.chatgpt_wrapper import ChatGPT


class PywrightDoer(ChatGPTDoer):
    def load_bot(self):
        bot = ChatGPT(headless=not self.debug)
        bot.conversation_id = self.state.get("conversation_id")
        bot.parent_message_id = self.state.get("parent_message_id")
        return bot

    def _ask(self, prompt: str) -> str:
        return self.bot.ask(prompt)

    def save_state(self):
        self.state["conversation_id"] = self.bot.conversation_id
        self.state["parent_message_id"] = self.bot.parent_message_id
        super().save_state()
