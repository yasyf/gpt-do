import re
import sqlite3
from dataclasses import dataclass, field
from functools import cached_property, wraps
from typing import Optional

import openai
import sqlparse
import sqlvalidator
from retry import retry
from tabulate import tabulate

from gpt_do.wtfers.wtfer import WTFer


def dedent(text: str) -> str:
    return "\n".join(map(str.strip, text.splitlines())).strip()


def truncate(content: str, length=300, suffix="\n(truncated)"):
    if len(content) <= length:
        return content
    else:
        try:
            idx = content.index("\n", length)
        except:
            idx = -1
        content = content[:idx] + suffix
        if len(content) < 2 * length:
            return content
        else:
            return suffix


def tab(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not (resp := list(map(dict, fn(*args, **kwargs)))):
            return None
        tabulate_args = {
            "headers": "keys",
            "missingval": "NULL",
            "maxheadercolwidths": 30,
        }
        tabulated = tabulate(resp, **tabulate_args, tablefmt="simple")
        if (truncated := truncate(tabulated)).count("-") / len(
            truncated.replace(" ", "")
        ) > 0.1:
            tabulated = tabulate(resp, **tabulate_args, tablefmt="plain")
            truncated = truncate(tabulated)

        return truncated if kwargs.get("truncate", True) else tabulated

    return wrapper


@dataclass
class Sample:
    MAX_RESULTS = 2
    SAFE_TABLES = {"sqlite_master", "sqlite_temp_master"}

    final: bool
    reason: str
    query: str
    original_query: str = field(init=False)
    errored: bool = False
    response: Optional[str] = None

    def __post_init__(self):
        self.original_query = self.query

    def is_empty(self):
        return self.query is None and self.reason is None and not self.final

    def format(self):
        return dedent(
            f"""
            FINAL: {self.final}
            REASON: {self.reason}

            START-QUERY
            {self.query}
            END-QUERY

            RESPONSE:
            {self.response}
            """
        )

    def _apply_limit(self, statement: sqlparse.sql.Statement, n=MAX_RESULTS):
        if any(t.match(sqlparse.tokens.Keyword, ["LIMIT"]) for t in statement):
            return statement

        tokens = statement.tokens.copy()

        try:
            index = statement.token_index(
                sqlparse.sql.Token(sqlparse.tokens.Punctuation, ";")
            )
        except ValueError:
            index = -1

        statement.tokens[index:index] = [
            sqlparse.sql.Token(sqlparse.tokens.Whitespace, " "),
            sqlparse.sql.Token(sqlparse.tokens.Keyword, "LIMIT"),
            sqlparse.sql.Token(sqlparse.tokens.Whitespace, " "),
            sqlparse.sql.Token(sqlparse.tokens.Number, n),
            sqlparse.sql.Token(sqlparse.tokens.Whitespace, " "),
        ]

        if not sqlvalidator.parse(str(statement)).is_valid():
            statement.tokens = tokens

        return statement

    def _relax_limit(self, statement: sqlparse.sql.Statement):
        if limit := next(
            (t for t in statement if t.match(sqlparse.tokens.Keyword, ["LIMIT"])), None
        ):
            _, n = statement.token_next(statement.token_index(limit))
            if n.value != "1":
                n.value = "25"
            return statement
        else:
            return self._apply_limit(statement, n=25)

    def _execute(self, curr: sqlite3.Cursor, statement: sqlparse.sql.Statement):
        self.query = str(statement)
        try:
            return curr.execute(self.query)
        except Exception as e:
            self.errored = True
            return curr.execute(f"SELECT 'Error: {e}. Try a different way.' as error")

    @tab
    def execute(
        self,
        curr: sqlite3.Cursor,
        statement: sqlparse.sql.Statement,
        truncate: bool,
    ):
        if truncate:
            statement = self._apply_limit(statement)
            return self._execute(curr, statement).fetchmany()
        else:
            if self.final:
                statement = self._relax_limit(statement)
            return self._execute(curr, statement).fetchall()

    def execute_and_format(
        self, curr: sqlite3.Cursor, statement: sqlparse.sql.Statement
    ):
        tokens = list(statement.flatten())

        try:
            from_ = next(t for t in tokens if t.match(sqlparse.tokens.Keyword, "FROM"))
            table = statement.token_next(statement.token_index(from_))[1].value
        except Exception:
            table = None

        select, pragma = (
            next((t for t in tokens if t.match(sqlparse.tokens.DML, "SELECT")), None),
            next((t for t in tokens if t.match(sqlparse.tokens.Name, "PRAGMA")), None),
        )

        if not (select or pragma):
            return None

        if select and not (parsed := sqlvalidator.parse(str(statement))).is_valid():
            return parsed.errors[0]

        return self.execute(
            curr,
            statement,
            truncate=not (self.final or pragma or table in self.SAFE_TABLES),
        )

    def populate(self, curr: sqlite3.Cursor):
        if not self.query:
            return
        statements = sqlparse.parse(self.original_query if self.final else self.query)
        results = filter(
            None,
            [self.execute_and_format(curr, statement) for statement in statements],
        )
        self.response = "\n".join(list(results))

    @classmethod
    def parse(cls, raw: str):
        if final_match := re.search(r"FINAL:\s*(?P<final>True|False)", raw, flags=re.I):
            final = final_match.group("final").lower() == "true"
        else:
            final = False

        if reason_match := re.search(r"REASON:\s*(?P<reason>.*)", raw):
            reason = reason_match.group("reason").strip()
        else:
            reason = ""

        if query_match := re.search(
            r"START-QUERY(?P<query>.*)END-QUERY", raw, re.DOTALL
        ):
            query = query_match.group("query").strip()
        elif not reason_match and not final_match:
            query = raw.strip().removeprefix("FINAL:").removesuffix("END-QUERY")
            if not sqlvalidator.parse(query).is_valid():
                query = ""
            elif not final_match:
                final = True
        else:
            query = ""

        return cls(final, reason, query)


class SQLWTFer(WTFer):
    MODELS = ["code-davinci-002", "text-davinci-003"]
    PROMPT_1 = dedent(
        """
    I have a task to perform on a SQLite database.

    The task is: {task}.

    Let's explain how we would solve this problem. Do not write any SQL yet.
    """
    )
    PROMPT_2 = dedent(
        """
    I have a task to perform on a SQLite database.

    Each time you respond, provide exactly one SQL query which will help you gather more information. I will give the responses of that query back to you.

    Do not return the final answer until you are confident. Do not include any information that you did not get from this specific database. Do not provide a response to the query; wait for me to do that.

    The task is: {task}.

    Now we will write the SQL, one statement at a time. Try to use as few queries as possible. Always use the following format.
    """
    )
    PROMPT_3 = dedent(
        """
    {history}

    So, the answer (in plain terms) to the original question is:
    """
    )
    EXAMPLES = [
        Sample(
            False,
            "I need to know what version of sqlite I am using.",
            "SELECT sqlite_version();",
        ),
        Sample(
            False,
            "I need to know what tables exist.",
            "SELECT name FROM sqlite_master WHERE type='table';",
        ),
    ]

    def __init__(
        self,
        db: str,
        task: str,
        model: str = MODELS[0],
        debug: bool = False,
    ) -> None:
        self.db = db
        self.task = task
        self.model = model
        self.debug = debug

        self.conn = sqlite3.connect(db)
        self._init_db()

        self._steps = ""
        self.examples = self.EXAMPLES.copy()

    def _init_db(self):
        self.conn.row_factory = sqlite3.Row
        self.curr = self.conn.cursor()
        self.curr.execute("PRAGMA query_only = 1;")
        self.curr.arraysize = Sample.MAX_RESULTS

    @cached_property
    @tab
    def tables(self):
        self.curr.execute(
            "SELECT name FROM sqlite_master WHERE type='table';"
        ).fetchall()

    @property
    def steps(self):
        if self.errors():
            return f"Let's think step by step.\n{self._steps}"
        else:
            return ""

    @property
    def prompt(self) -> str:
        samples = "\n".join(map(Sample.format, self.examples))
        prompt = self.PROMPT_2.format(task=self.task)
        return dedent(
            f"""
            {prompt}
            {samples}
            {self.steps}

            FINAL:
            """
        )

    @cached_property
    def result(self):
        result = next(s for s in reversed(self.examples) if s.query)
        result.final = True
        return result

    def execute(self):
        self.result.populate(self.curr)
        return next(s for s in reversed(self.examples) if s.response).response

    def errors(self):
        return len([s for s in reversed(self.examples) if s.errored])

    def next_model(self):
        return next(m for m in self.MODELS if m != self.model)

    @retry(tries=3, delay=0.5, backoff=1.1, jitter=(-0.1, 0.1))
    def _query(self):
        penalties = {"frequency_penalty": 0.5}

        if (errors := self.errors()) == 1:
            penalties = {"frequency_penalty": 1.5, "presence_penalty": 0.5}
        elif errors > 1:
            self.dprint("Too many errors, switching models")
            self.model = self.next_model()
            for _ in range(errors):
                self.examples.pop()

        try:
            self.dprint("*Query*\n", self.model, len(self.prompt))
            return openai.Completion.create(
                engine=self.model,
                prompt=self.prompt,
                stop="END-QUERY",
                temperature=0,
                max_tokens=256,
                request_timeout=10,
                **penalties,
            )
        except openai.error.RateLimitError as e:
            self.dprint("Error:", e)
            self.model = self.next_model()
            raise
        except openai.error.APIError as e:
            self.dprint("Error:", e)
            if "maximum context length" in str(e):
                self.examples[-1].response = "(too long)"
            raise

    @retry(tries=3, delay=1, backoff=1.2)
    def prime(self):
        steps = (
            openai.Completion.create(
                engine=self.model,
                prompt=self.PROMPT_1.format(task=self.task),
                temperature=0,
                max_tokens=256,
                request_timeout=30,
            )
            .choices[0]
            .text
        )

        self.dprint("*Steps*\n", steps)
        self._steps = steps

        for example in self.examples:
            example.populate(self.curr)

    def answer(self):
        if not self.result.response:
            self.execute()
        return (
            openai.Completion.create(
                engine=self.model,
                prompt=self.PROMPT_3.format(history=self.prompt),
                temperature=0,
                max_tokens=256,
                request_timeout=30,
            )
            .choices[0]
            .text
        )

    def __iter__(self):
        self.prime()
        self.dprint("*Initial Prompt*\n", self.prompt)
        return self

    def __next__(self):
        try:
            self.examples[-1].populate(self.curr)
            self.dprint("*Result*\n", self.examples[-1].response)
        except StopIteration as e:
            self.examples[-1].response = f"Error: {e}"
            if self.debug:
                raise Exception from e

        raw = self._query().choices[0].text
        self.dprint("*Raw Response*\n", raw)

        try:
            sample = Sample.parse(f"FINAL: {raw}\nEND-QUERY")
        except StopIteration as e:
            sample = Sample(False, "", "", f"Error: {e}")

        if not sample.is_empty():
            self.examples.append(sample)
        self.dprint(sample)

        if sample.final:
            sample.populate(self.curr)
            if sample.errored:
                sample.final = False
                return sample
            else:
                raise StopIteration()
        else:
            return sample
