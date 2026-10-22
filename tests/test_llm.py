import pytest
from pydantic import ValidationError

from src.llm import LLMResponse, Message, MockLLMClient, MockLLMExhaustedError, ToolCall
from src.schemas import ParseJobArguments, ToolResult
from src.tool_registry import ToolRegistry, create_tool_registry


def test_schemas_match_execution_models_and_registered_tools(tmp_path):
    registry = create_tool_registry(tmp_path)
    schemas = {tool.name: tool for tool in registry.get_tool_schemas()}
    assert set(schemas) == {"read_resume", "parse_job", "find_evidence"}
    assert schemas["parse_job"].parameters == ParseJobArguments.model_json_schema()
    for schema in schemas.values():
        assert schema.description.strip()
        assert schema.parameters["additionalProperties"] is False
    assert "allowed_directory" not in schemas["read_resume"].parameters["properties"]
    assert ToolRegistry().get_tool_schemas() == []


def test_custom_registration_is_visible_without_a_second_tool_definition():
    registry = ToolRegistry()
    registry.register("custom", ParseJobArguments, lambda jd_text: jd_text, description="Custom tool")
    schema = registry.get_tool_schemas()[0]
    assert schema.name == "custom"
    assert schema.description == "Custom tool"
    assert schema.parameters == ParseJobArguments.model_json_schema()
    assert registry.execute(schema.name, {"jd_text": "test"}).data == "test"
    schema.parameters["properties"].clear()
    assert registry.get_tool_schemas()[0].parameters["properties"]


@pytest.mark.parametrize("payload", [
    {},
    {"final_answer": ""},
    {"final_answer": "  "},
    {"final_answer": 1},
    {"tool_calls": []},
    {"final_answer": "done", "tool_calls": [{"id": "1", "name": "parse_job", "arguments": {}}]},
    {"tool_calls": [
        {"id": "same", "name": "parse_job", "arguments": {}},
        {"id": "same", "name": "parse_job", "arguments": {}},
    ]},
])
def test_response_rejects_invalid_or_ambiguous_decisions(payload):
    with pytest.raises(ValidationError):
        LLMResponse.model_validate(payload)


@pytest.mark.parametrize("payload", [
    {"id": "", "name": "parse_job", "arguments": {}},
    {"id": " ", "name": "parse_job", "arguments": {}},
    {"id": "1", "name": " ", "arguments": {}},
    {"id": "1", "name": "parse_job", "arguments": "{}"},
    {"id": "1", "name": "parse_job", "arguments": {}, "extra": True},
])
def test_tool_call_validates_envelope_but_leaves_arguments_for_registry(payload):
    with pytest.raises(ValidationError):
        ToolCall.model_validate(payload)
    # Unknown names and wrong argument fields still reach the executor as recoverable errors.
    assert ToolCall(id="x", name="not_registered", arguments={"anything": 42})


@pytest.mark.parametrize("payload", [
    {"role": "user", "content": " "},
    {"role": "user", "content": "hi", "tool_call_id": "x"},
    {"role": "assistant"},
    {"role": "tool", "tool_call_id": "x"},
    {"role": "tool", "tool_result": ToolResult(tool_name="x", success=True)},
])
def test_message_enforces_role_payload(payload):
    with pytest.raises(ValidationError):
        Message.model_validate(payload)


def test_mock_replays_and_snapshots_without_mutating_inputs():
    first = LLMResponse(tool_calls=[ToolCall(id="1", name="parse_job", arguments={"jd_text": "Intern"})])
    mock = MockLLMClient([first, LLMResponse(final_answer="done")])
    first.tool_calls[0].arguments["jd_text"] = "changed outside"
    messages = [Message(role="user", content="task")]
    tools = create_tool_registry().get_tool_schemas()
    response = mock.complete(messages, tools)
    assert response.tool_calls[0].arguments == {"jd_text": "Intern"}
    messages[0].content = "changed"
    tools[0].parameters.clear()
    assert mock.requests[0].messages[0].content == "task"
    assert mock.requests[0].tools[0].parameters
    assert mock.complete(messages, []).final_answer == "done"
    with pytest.raises(MockLLMExhaustedError):
        mock.complete(messages, [])


def test_mock_can_script_a_model_exception():
    mock = MockLLMClient([RuntimeError("scripted")])
    with pytest.raises(RuntimeError, match="scripted"):
        mock.complete([Message(role="user", content="task")], [])
