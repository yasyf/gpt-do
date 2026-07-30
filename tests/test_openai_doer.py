from types import SimpleNamespace
from unittest.mock import Mock, patch

import click
import pytest
from click.testing import CliRunner

from gpt_do.cli.do import do
from gpt_do.doers.gpt3_doer import OpenAIDoer


@pytest.fixture
def click_context():
    with click.Context(click.Command("ddo")):
        yield


def test_uses_responses_api_with_selected_model(monkeypatch, tmp_path, click_context):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    client = Mock()
    client.responses.create.return_value = SimpleNamespace(
        output_text='{"commands":["pwd"],"explanation":"Print the working directory."}'
    )

    with patch("gpt_do.doers.gpt3_doer.OpenAI", return_value=client):
        doer = OpenAIDoer(model="gpt-5-mini")
        doer.__dict__["_history"] = []
        result = doer.ask("show my current directory", is_json=True)

    assert result["commands"] == ["pwd"]
    request = client.responses.create.call_args.kwargs
    assert request["model"] == "gpt-5-mini"
    assert request["input"] == "show my current directory"
    assert request["text"]["format"]["type"] == "json_schema"


def test_requires_api_key(monkeypatch, tmp_path, click_context):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))

    with pytest.raises(click.UsageError, match="OPENAI_API_KEY"):
        OpenAIDoer(model="gpt-5-mini")


def test_cli_accepts_current_model_ids():
    result = CliRunner().invoke(do, ["--model", "gpt-5.4-mini", "--help"])

    assert result.exit_code == 0
    assert "OpenAI model ID to use" in result.output
