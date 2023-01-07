import re
import sqlite3
from dataclasses import dataclass
from functools import cached_property, wraps
from typing import Optional

import openai
import sqlparse
from retry import retry
from tabulate import tabulate

from gpt_do.wtfers.wtfer import WTFer


def dedent(text: str) -> str:
    return "\n".join(map(str.strip, text.splitlines()))


def truncate(content: str, length=1000, suffix="\n(truncated)"):
    if len(content) <= length:
        return content
    else:
        return content[: content.index("\n", length)] + suffix


def tab(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        do_truncate = kwargs.pop("truncate", True)
        resp = list(map(dict, fn(*args, **kwargs)))
        tabulate_args = {"headers": "keys", "missingval": "NONE"}
        tabulated = tabulate(resp, **tabulate_args, tablefmt="simple")
        if (truncated := truncate(tabulated)).count("-") / len(truncated) > 0.1:
            tabulated = tabulate(resp, **tabulate_args, tablefmt="plain")
            truncated = truncate(tabulated)

        return truncated if do_truncate else tabulated

    return wrapper


@dataclass
class Sample:
    MAX_RESULTS = 2

    final: bool
    reason: str
    query: str
    response: Optional[str] = None

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

    def _apply_limit(self, statement: sqlparse.sql.Statement):
        if any(t.match(sqlparse.tokens.Keyword, ["LIMIT"]) for t in statement):
            return statement

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
            sqlparse.sql.Token(sqlparse.tokens.Number, self.MAX_RESULTS),
        ]
        return statement

    def _relax_limit(self, statement: sqlparse.sql.Statement):
        if limit := next(
            (t.match(sqlparse.tokens.Keyword, ["LIMIT"]) for t in statement), None
        ):
            _, n = statement.token_next(statement.token_index(limit))
            n.value = "100"

        return statement

    def _execute(self, curr: sqlite3.Cursor, statement: sqlparse.sql.Statement):
        self.query = str(statement)
        try:
            return curr.execute(self.query)
        except Exception as e:
            self.query = f"SELECT '{e}' as error"
            return curr.execute(self.query)

    @tab
    def execute(self, curr: sqlite3.Cursor, statement: sqlparse.sql.Statement):
        tokens = list(statement.flatten())

        select = next(
            (t for t in tokens if t.match(sqlparse.tokens.DML, "SELECT")), None
        )
        pragma = next(
            (t for t in tokens if t.match(sqlparse.tokens.Name, "PRAGMA")), None
        )

        if not (select or pragma):
            return []

        if pragma:
            return self._execute(curr, statement).fetchall()

        from_ = next(t for t in tokens if t.match(sqlparse.tokens.Keyword, "FROM"))
        table = statement.token_next(statement.token_index(from_))

        if (
            table
            and table[1]
            and table[1].value in {"sqlite_master", "sqlite_temp_master"}
        ):
            return self._execute(curr, statement).fetchall()
        else:
            if self.final:
                sql = self._relax_limit(statement)
            else:
                sql = self._apply_limit(statement)
            return self._execute(curr, sql).fetchmany()

    def populate(self, curr: sqlite3.Cursor):
        if self.response or not self.query:
            return
        statements = sqlparse.parse(self.query)
        results = filter(
            None,
            [
                self.execute(curr, statement, truncate=not self.final)
                for statement in statements
            ],
        )
        self.response = "\n".join(list(results))

    @classmethod
    def parse(cls, raw: str):
        if match := re.search(r"FINAL: (?P<final>True|False)", raw):
            final = match.group("final").lower() == "true"
        else:
            final = True

        if match := re.search(r"REASON: (?P<reason>.*)", raw):
            reason = match.group("reason").strip()
        else:
            reason = ""

        if match := re.search(r"START-QUERY(?P<query>.*)END-QUERY", raw, re.DOTALL):
            query = match.group("query").strip()
        else:
            query = ""

        return cls(final, reason, query)


class SQLWTFer(WTFer):
    PROMPT = dedent(
        """
    I have a task to perform on a SQLite database. You must provide a response in SQL.

    Each time you respond, provide exactly one SQL query which will help you gather more information. I will give the responses of that query back to you.

    Do not return the final answer until you are confident. Do not include any information that you did not get from this specific database. Do not provide a response to the query; wait for me to do that.

    The task is: {task}.
    """
    )
    EXAMPLES = [
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
        model: str = "code-davinci-002",
        debug: bool = False,
    ) -> None:
        self.db = db
        self.task = task
        self.model = model
        self.debug = debug

        self.conn = sqlite3.connect(db)
        self._init_db()

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
    def prompt(self) -> str:
        samples = "\n".join(map(Sample.format, self.examples))
        return dedent(
            f"""
            {self.PROMPT.format(task=self.task)}
            {samples}

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

    @retry(tries=3, delay=0.5, backoff=1.1, jitter=(-0.1, 0.1))
    def _query(self):
        try:
            return openai.Completion.create(
                engine=self.model,
                prompt=self.prompt,
                stop="END-QUERY",
                temperature=0,
                max_tokens=256,
                request_timeout=10,
                frequency_penalty=0.1,
            )
        except openai.error.APIError as e:
            if "maximum context length" in str(e):
                self.examples[-1].response = "(too long)"
            raise

    def __iter__(self):
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

        self.examples.append(sample)
        self.dprint(sample)

        if sample.final:
            raise StopIteration()
        else:
            return sample
