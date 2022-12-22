import openai

from do.doers.doer import Doer


class GPT3Doer(Doer):
    model = "text-davinci-003"

    def load_bot(self):
        pass

    def prime_convo(self):
        self.dprint(self.prompt)

    def _ask(self, prompt: str) -> str:
        contents = openai.Completion.create(
            engine=self.__class__.model,
            prompt=f"{self.prompt}\nRequest: {prompt}\n{{",
            stop="}",
            temperature=0,
            max_tokens=256,
        )
        self.dprint(contents)
        return "{" + contents.choices[0]["text"] + "}"
