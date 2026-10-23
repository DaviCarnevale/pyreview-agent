"""Automated unit and integration tests for ReviewAgent and tool calling loop."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import openai
import pytest

from agent.core import ReviewAgent
from agent.tools import CodeInspector
from config.settings import Settings, get_settings


class MockFunction:
    def __init__(self, name: str, arguments: str):
        self.name = name
        self.arguments = arguments


class MockToolCall:
    def __init__(self, call_id: str, fn_name: str, fn_args: str):
        self.id = call_id
        self.type = "function"
        self.function = MockFunction(fn_name, fn_args)


class MockMessage:
    def __init__(self, content: str | None = None, tool_calls: list | None = None):
        self.content = content
        self.tool_calls = tool_calls or []


class MockChoice:
    def __init__(self, message: MockMessage):
        self.message = message


class MockCompletionResponse:
    def __init__(self, message: MockMessage):
        self.choices = [MockChoice(message)]


@pytest.fixture
def test_settings() -> Settings:
    """Fixture providing test configuration settings."""
    return Settings(
        openai_api_key="sk-test-key-12345",
        openai_model="gpt-4o-mini",
        openai_temperature=0.0,
        max_agent_iterations=5,
        max_file_lines=100,
        max_file_bytes=50000,
    )


@pytest.fixture
def mock_project(tmp_path: Path) -> Path:
    """Fixture creating a minimal project structure."""
    main_code = "def add(a: int, b: int) -> int:\n    return a + b\n"
    (tmp_path / "main.py").write_text(main_code, encoding="utf-8")
    return tmp_path


def test_settings_validation():
    """Test Pydantic configuration validation."""
    s = Settings(openai_api_key="  sk-secret  ")
    assert s.openai_api_key == "sk-secret"
    assert s.openai_model == "gpt-4o-mini"
    assert s.max_agent_iterations == 12

    # Validation failure when key is empty
    empty_settings = Settings(openai_api_key="")
    with pytest.raises(ValueError, match="OPENAI_API_KEY is missing"):
        empty_settings.validate_api_key()


def test_agent_tool_calling_lifecycle(mock_project: Path, test_settings: Settings):
    """Test the complete multi-turn tool calling cycle using mocked OpenAI completions."""
    inspector = CodeInspector(base_dir=mock_project)
    mock_client = MagicMock()

    # Turn 1: Model calls list_python_files
    call_1 = MockToolCall("call_1", "list_python_files", json.dumps({"relative_subdir": "."}))
    resp_1 = MockCompletionResponse(MockMessage(content=None, tool_calls=[call_1]))

    # Turn 2: Model calls read_python_file for main.py
    call_2 = MockToolCall("call_2", "read_python_file", json.dumps({"file_path": "main.py"}))
    resp_2 = MockCompletionResponse(MockMessage(content=None, tool_calls=[call_2]))

    # Turn 3: Model outputs final structured code review report
    final_report_text = "# Code Review Report\nEverything looks great!"
    resp_3 = MockCompletionResponse(MockMessage(content=final_report_text, tool_calls=[]))

    mock_client.chat.completions.create.side_effect = [resp_1, resp_2, resp_3]

    agent = ReviewAgent(inspector=inspector, settings=test_settings, client=mock_client)

    progress_events = []

    def record_progress(event: str):
        progress_events.append(event)

    result = agent.review_project(progress_callback=record_progress)

    # Assertions
    assert result == final_report_text
    assert mock_client.chat.completions.create.call_count == 3
    assert len(progress_events) == 2
    assert "Listing Python files" in progress_events[0]
    assert "Inspecting code in 'main.py'" in progress_events[1]

    # Verify message sequence in conversation history
    # 0: system, 1: user, 2: assistant(tc1), 3: tool(tc1), 4: assistant(tc2), 5: tool(tc2), 6: assistant(final)
    messages = agent.messages
    assert len(messages) == 7
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"
    assert messages[2]["tool_calls"][0]["id"] == "call_1"
    assert messages[3]["role"] == "tool"
    assert messages[3]["tool_call_id"] == "call_1"
    assert "main.py" in messages[3]["content"]
    assert messages[4]["role"] == "assistant"
    assert messages[4]["tool_calls"][0]["id"] == "call_2"
    assert messages[5]["role"] == "tool"
    assert messages[5]["tool_call_id"] == "call_2"
    assert "add(a: int, b: int)" in messages[5]["content"]
    assert messages[6]["role"] == "assistant"
    assert messages[6]["content"] == final_report_text


def test_agent_interactive_ask(mock_project: Path, test_settings: Settings):
    """Test that interactive follow-up questions preserve previous conversation history."""
    inspector = CodeInspector(base_dir=mock_project)
    mock_client = MagicMock()

    resp_initial = MockCompletionResponse(MockMessage(content="Initial Review", tool_calls=[]))
    resp_followup = MockCompletionResponse(MockMessage(content="Here is how to refactor add().", tool_calls=[]))

    mock_client.chat.completions.create.side_effect = [resp_initial, resp_followup]

    agent = ReviewAgent(inspector=inspector, settings=test_settings, client=mock_client)
    agent.review_project()

    # User asks a follow-up
    answer = agent.ask("Can you explain how to optimize add()?")

    assert answer == "Here is how to refactor add()."
    # Ensure follow up question is in messages
    assert agent.messages[-2]["role"] == "user"
    assert agent.messages[-2]["content"] == "Can you explain how to optimize add()?"
    assert agent.messages[-1]["role"] == "assistant"
    assert agent.messages[-1]["content"] == "Here is how to refactor add()."


def test_agent_handles_authentication_error(mock_project: Path, test_settings: Settings):
    """Ensure AuthenticationError produces a clear message without crash."""
    inspector = CodeInspector(base_dir=mock_project)
    mock_client = MagicMock()

    mock_client.chat.completions.create.side_effect = openai.AuthenticationError(
        message="Incorrect API key provided.",
        response=MagicMock(status_code=401),
        body=None,
    )

    agent = ReviewAgent(inspector=inspector, settings=test_settings, client=mock_client)
    res = agent.review_project()

    assert "⚠️ Authentication Error" in res
    assert "Incorrect API key" in res


def test_agent_handles_rate_limit_error(mock_project: Path, test_settings: Settings):
    """Ensure RateLimitError produces a clear user notification."""
    inspector = CodeInspector(base_dir=mock_project)
    mock_client = MagicMock()

    mock_client.chat.completions.create.side_effect = openai.RateLimitError(
        message="Rate limit reached for requests.",
        response=MagicMock(status_code=429),
        body=None,
    )

    agent = ReviewAgent(inspector=inspector, settings=test_settings, client=mock_client)
    res = agent.review_project()

    assert "⚠️ Rate Limit Error" in res
    assert "quota or rate limit exceeded" in res


def test_agent_handles_api_connection_error(mock_project: Path, test_settings: Settings):
    """Ensure APIConnectionError produces a clear network failure notification."""
    inspector = CodeInspector(base_dir=mock_project)
    mock_client = MagicMock()

    mock_client.chat.completions.create.side_effect = openai.APIConnectionError(
        request=MagicMock()
    )

    agent = ReviewAgent(inspector=inspector, settings=test_settings, client=mock_client)
    res = agent.review_project()

    assert "⚠️ Connection Error" in res


def test_agent_max_iterations_reached(mock_project: Path, test_settings: Settings):
    """Ensure agent terminates if max_iterations threshold is reached without completion."""
    test_settings.max_agent_iterations = 2
    inspector = CodeInspector(base_dir=mock_project)
    mock_client = MagicMock()

    # Keep returning tool calls continuously
    infinite_tool_call = MockToolCall("call_loop", "list_python_files", json.dumps({"relative_subdir": "."}))
    loop_resp = MockCompletionResponse(MockMessage(content=None, tool_calls=[infinite_tool_call]))

    mock_client.chat.completions.create.return_value = loop_resp

    agent = ReviewAgent(inspector=inspector, settings=test_settings, client=mock_client)
    res = agent.review_project()

    assert "reached maximum iteration limit" in res
    assert mock_client.chat.completions.create.call_count == 2
