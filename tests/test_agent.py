import pytest

from src.agent import Agent
from src.llm import LLMResponse, MockLLMClient, ToolCall
from src.schemas import ParseJobArguments
from src.tool_registry import ToolRegistry, create_tool_registry


def call_response(call_id="job", name="parse_job", **arguments):
    return LLMResponse(tool_calls=[ToolCall(id=call_id, name=name, arguments=arguments)])


def tool_messages(result):
    return [message for message in result.messages if message.role == "tool"]


def test_model_direct_final_answer():
    mock = MockLLMClient([LLMResponse(final_answer="Hello")])
    result = Agent(mock, ToolRegistry()).run("Say hello")
    assert result.status == "completed"
    assert result.final_answer == "Hello"
    assert result.error_code is None
    assert result.steps == 1
    assert [message.role for message in result.messages] == ["user", "assistant"]
    assert len(mock.requests) == 1
    assert mock.requests[0].tools == []
    assert result.trace[0].decision == "final_answer"


def test_one_tool_then_final_answer_uses_executor_and_delivers_result(monkeypatch):
    registry = create_tool_registry()
    actual_execute = registry.execute
    executions = []

    def execute(name, arguments):
        executions.append((name, arguments))
        return actual_execute(name, arguments)

    monkeypatch.setattr(registry, "execute", execute)
    mock = MockLLMClient([
        call_response(jd_text="AI Intern\nRequired: Python"),
        LLMResponse(final_answer="Scripted completion"),
    ])
    result = Agent(mock, registry).run("Analyze JD")
    assert result.status == "completed"
    assert result.steps == 2
    assert executions == [("parse_job", {"jd_text": "AI Intern\nRequired: Python"})]
    assert [message.role for message in result.messages] == ["user", "assistant", "tool", "assistant"]
    assert result.messages[1].tool_calls[0].id == "job"
    message = mock.requests[1].messages[-1]
    assert message.tool_call_id == "job"
    assert message.tool_result.tool_name == "parse_job"
    assert message.tool_result.data["required_skills"] == ["Python"]
    assert len(mock.requests[0].messages) == 1  # Snapshot does not grow with history.
    assert {schema.name for schema in mock.requests[0].tools} == {
        "read_resume", "parse_job", "find_evidence",
    }


def test_multiple_rounds_of_tools(tmp_path):
    path = tmp_path / "resume.txt"
    path.write_text("Python project", encoding="utf-8")
    mock = MockLLMClient([
        call_response("resume", "read_resume", file_path=str(path)),
        call_response("jd", jd_text="Intern\nPython and SQL"),
        call_response("evidence", "find_evidence", resume_text="Python project", skills=["Python", "SQL"]),
        LLMResponse(final_answer="Scripted final answer"),
    ])
    result = Agent(mock, create_tool_registry(tmp_path)).run("Analyze resume and JD")
    assert result.status == "completed"
    assert result.steps == 4
    assert [len(request.messages) for request in mock.requests] == [1, 3, 5, 7]
    results = tool_messages(result)
    assert [message.tool_call_id for message in results] == ["resume", "jd", "evidence"]
    assert results[-1].tool_result.data[1] == {"skill": "SQL", "found": False, "evidence": []}


def test_multiple_tools_same_round_preserve_order_and_ids():
    mock = MockLLMClient([
        LLMResponse(tool_calls=[
            ToolCall(id="job-2", name="parse_job", arguments={"jd_text": "Intern\nSQL"}),
            ToolCall(id="evidence-1", name="find_evidence", arguments={"resume_text": "Python project", "skills": ["Python"]}),
        ]),
        LLMResponse(final_answer="done"),
    ])
    result = Agent(mock, create_tool_registry()).run("task")
    assert result.status == "completed"
    results = mock.requests[1].messages[2:]
    assert [message.tool_call_id for message in results] == ["job-2", "evidence-1"]
    assert [message.tool_result.tool_name for message in results] == ["parse_job", "find_evidence"]
    assert results[0].tool_result.data["required_skills"] == ["SQL"]
    assert results[1].tool_result.data[0]["found"] is True


@pytest.mark.parametrize("name, arguments, code", [
    ("not_registered", {}, "unknown_tool"),
    ("parse_job", {}, "invalid_arguments"),
    ("parse_job", {"jd_text": 123}, "invalid_arguments"),
    ("parse_job", {"jd_text": "Intern", "extra": True}, "invalid_arguments"),
])
def test_recoverable_error_returned_to_model_before_retry(name, arguments, code):
    mock = MockLLMClient([
        call_response("bad", name, **arguments),
        call_response("retry", jd_text="Intern\nPython"),
        LLMResponse(final_answer="done"),
    ])
    result = Agent(mock, create_tool_registry()).run("task")
    assert result.status == "completed"
    assert result.steps == 3
    error_message = mock.requests[1].messages[-1]
    assert error_message.tool_call_id == "bad"
    assert error_message.tool_result.error.code == code
    assert not error_message.tool_result.success
    assert mock.requests[2].messages[-1].tool_result.success
    assert result.trace[1].error_code == code


@pytest.mark.parametrize("kind, code", [("missing", "file_not_found"), ("outside", "access_denied")])
def test_fatal_file_errors_stop_without_trying_another_path(tmp_path, monkeypatch, kind, code):
    root = tmp_path / "allowed"
    root.mkdir()
    initial_path = (root if kind == "missing" else tmp_path) / "missing.txt"
    safe_path = root / "resume.txt"
    safe_path.write_text("Should never be read", encoding="utf-8")
    registry = create_tool_registry(root)
    executions = []
    actual_execute = registry.execute

    def execute(name, arguments):
        executions.append(arguments)
        return actual_execute(name, arguments)

    monkeypatch.setattr(registry, "execute", execute)
    mock = MockLLMClient([
        LLMResponse(tool_calls=[
            ToolCall(id="fatal", name="read_resume", arguments={"file_path": str(initial_path)}),
            ToolCall(id="same-batch-bypass", name="read_resume", arguments={"file_path": str(safe_path)}),
        ]),
        call_response("next-round-bypass", "read_resume", file_path=str(safe_path)),
    ])
    result = Agent(mock, registry).run("Read resume")
    assert result.status == "tool_error"
    assert result.error_code == code
    assert result.final_answer is None
    assert result.steps == len(mock.requests) == len(executions) == 1
    assert "停止" in result.message
    if kind == "missing":
        assert "正确" in result.message and "不会扫描" in result.message
    results = tool_messages(result)
    assert [message.tool_call_id for message in results] == ["fatal", "same-batch-bypass"]
    assert [message.tool_result.error.code for message in results] == [code, "not_executed"]
    assert result.trace[-2].event == "tool_skipped"


def test_step_limit_is_not_success_even_when_tools_succeed():
    mock = MockLLMClient([call_response(str(index), jd_text="Intern") for index in range(4)])
    result = Agent(mock, create_tool_registry(), max_steps=3).run("task")
    assert result.status == "step_limit"
    assert result.error_code == "max_steps_exceeded"
    assert result.final_answer is None
    assert result.steps == len(mock.requests) == 3
    assert len(tool_messages(result)) == 3
    assert all(message.tool_result.success for message in tool_messages(result))
    assert not result.trace[-1].success


def test_recoverable_errors_are_also_bounded():
    mock = MockLLMClient([call_response(str(index), "unknown") for index in range(2)])
    result = Agent(mock, ToolRegistry(), max_steps=2).run("task")
    assert result.status == "step_limit"
    assert len(mock.requests) == 2


def test_final_answer_on_last_step_is_success():
    mock = MockLLMClient([call_response(jd_text="Intern"), LLMResponse(final_answer="done")])
    assert Agent(mock, create_tool_registry(), max_steps=2).run("task").status == "completed"


@pytest.mark.parametrize("max_steps", [0, -1, True, 1.5, "2", None])
def test_max_steps_must_be_positive_integer(max_steps):
    with pytest.raises(ValueError):
        Agent(MockLLMClient([]), ToolRegistry(), max_steps=max_steps)


@pytest.mark.parametrize("failure", [RuntimeError("private API key"), TimeoutError("private resume")])
def test_model_exception_stops_and_is_redacted(failure, capsys, caplog):
    mock = MockLLMClient([failure, LLMResponse(final_answer="must not run")])
    result = Agent(mock, ToolRegistry()).run("task")
    assert result.status == "model_error"
    assert result.error_code == "model_exception"
    assert result.steps == len(mock.requests) == 1
    assert result.final_answer is None
    assert "private" not in result.model_dump_json()
    assert capsys.readouterr().out == ""
    assert caplog.text == ""


def test_mock_exhaustion_is_model_error():
    result = Agent(MockLLMClient([]), ToolRegistry()).run("task")
    assert result.status == "model_error"


def test_reused_call_ids_fail_before_second_execution():
    mock = MockLLMClient([
        call_response("same", jd_text="Intern"),
        call_response("same", jd_text="Python"),
    ])
    result = Agent(mock, create_tool_registry()).run("task")
    assert result.status == "model_error"
    assert result.error_code == "invalid_model_response"
    assert len(tool_messages(result)) == 1


@pytest.mark.parametrize("response", [
    LLMResponse.model_construct(final_answer=None, tool_calls=[]),
    LLMResponse.model_construct(final_answer="done", tool_calls=[
        ToolCall(id="x", name="parse_job", arguments={"jd_text": "Intern"}),
    ]),
])
def test_agent_revalidates_constructed_responses(response):
    result = Agent(MockLLMClient([response]), create_tool_registry()).run("task")
    assert result.status == "model_error"
    assert result.error_code == "invalid_model_response"
    assert tool_messages(result) == []


def test_trace_and_console_omit_sensitive_task_arguments_results_and_exceptions(tmp_path, capsys, caplog):
    secret = "SYNTHETIC_PRIVATE_RESUME_7788"
    path = tmp_path / "private-resume.txt"
    path.write_text(secret, encoding="utf-8")
    mock = MockLLMClient([
        call_response("read", "read_resume", file_path=str(path)),
        call_response("evidence", "find_evidence", resume_text=secret, skills=[secret]),
        LLMResponse(final_answer=secret),
    ])
    result = Agent(mock, create_tool_registry(tmp_path)).run(f"Analyze {secret}")
    assert result.status == "completed"
    assert secret in result.model_dump_json()  # History is model context, not a log.
    log = "\n".join(event.model_dump_json() for event in result.trace)
    assert secret not in log
    assert str(path) not in log
    assert "resume_text" not in log
    assert "arguments" not in log
    assert capsys.readouterr().out == ""
    assert caplog.text == ""


def test_nonrecoverable_tool_exception_is_distinct_from_model_error():
    def broken(jd_text):
        raise RuntimeError("sensitive exception")

    registry = ToolRegistry()
    registry.register("broken", ParseJobArguments, broken)
    mock = MockLLMClient([call_response("broken", "broken", jd_text="Intern")])
    result = Agent(mock, registry).run("task")
    assert result.status == "tool_error"
    assert result.error_code == "execution_error"
    assert "sensitive" not in result.model_dump_json()


def test_unexpected_executor_exception_is_also_tool_error(monkeypatch):
    registry = create_tool_registry()

    def broken(*args):
        raise RuntimeError("sensitive executor failure")

    monkeypatch.setattr(registry, "execute", broken)
    mock = MockLLMClient([call_response(jd_text="Intern")])
    result = Agent(mock, registry).run("task")
    assert result.status == "tool_error"
    assert result.error_code == "execution_error"
    assert "sensitive" not in result.model_dump_json()


def test_unknown_tool_name_cannot_copy_private_text_into_trace():
    secret = "SYNTHETIC_PRIVATE_TEXT_AS_TOOL_NAME"
    mock = MockLLMClient([call_response("x", secret), LLMResponse(final_answer="done")])
    result = Agent(mock, ToolRegistry()).run("task")
    assert result.status == "completed"
    assert secret not in "\n".join(event.model_dump_json() for event in result.trace)
    assert result.trace[1].tool_name == "<unregistered>"


@pytest.mark.parametrize("task", ["", " \n", None, 123])
def test_invalid_user_task_is_rejected_before_model_call(task):
    mock = MockLLMClient([])
    with pytest.raises(ValueError):
        Agent(mock, ToolRegistry()).run(task)
    assert mock.requests == []
