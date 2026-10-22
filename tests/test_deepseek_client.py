import json
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import pytest
from openai import APIConnectionError, APITimeoutError, RateLimitError
from openai.types.chat import ChatCompletion

from src.agent import Agent
from src.deepseek import BASE_URL, DeepSeekClientError, DeepSeekLLMClient
from src.llm import Message, ToolCall
from src.schemas import ToolError, ToolResult
from src.tool_registry import create_tool_registry


class FakeSDK:
    """Implements only the SDK surface used by the adapter; never has a transport."""

    def __init__(self, responses):
        self.responses = iter(responses)
        self.requests = []
        self.closed = False
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        response = next(self.responses)
        if isinstance(response, Exception):
            raise response
        return response

    def close(self):
        self.closed = True


def completion(content="done", *, calls=None, finish_reason=None):
    """Use real SDK response types to exercise its tool-call attribute layout."""
    return ChatCompletion.model_validate({
        "id": "completion-test", "object": "chat.completion", "created": 0,
        "model": "test-model", "choices": [{
            "index": 0, "finish_reason": finish_reason or ("tool_calls" if calls else "stop"),
            "message": {"role": "assistant", "content": content, "tool_calls": calls},
        }],
    })


def tool_call(call_id="job-call", name="parse_job", arguments='{"jd_text":"Intern\\nPython"}'):
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": arguments}}


@pytest.fixture(autouse=True)
def forbid_actual_sdk_requests(monkeypatch):
    # Even a test regression cannot reach the real SDK network method.
    from openai.resources.chat.completions import Completions

    def forbidden(*args, **kwargs):
        raise AssertionError("Real SDK requests are forbidden in adapter tests")

    monkeypatch.setattr(Completions, "create", forbidden)


def test_final_answer_and_bounded_sdk_request():
    sdk = FakeSDK([completion("分析完成")])
    client = DeepSeekLLMClient(sdk_client=sdk, model="test-model", max_tokens=256, timeout=12)
    result = client.complete([Message(role="user", content="任务")], [])
    assert result.final_answer == "分析完成"
    assert result.tool_calls == []
    assert sdk.requests == [{
        "model": "test-model", "messages": [{"role": "user", "content": "任务"}],
        "max_tokens": 256, "timeout": 12, "stream": False, "n": 1,
        "extra_body": {"thinking": {"type": "disabled"}},
    }]
    assert client.request_count == 1
    assert client.last_error_code is None
    client.close()
    assert sdk.closed


def test_registry_schema_and_multiple_response_calls_are_converted():
    sdk = FakeSDK([completion("先查询工具", calls=[
        tool_call("one"),
        tool_call("two", "find_evidence", '{"resume_text":"Python 项目","skills":["Python"]}'),
    ])])
    tools = create_tool_registry().get_tool_schemas()
    result = DeepSeekLLMClient(sdk_client=sdk).complete([Message(role="user", content="task")], tools)
    assert result.final_answer is None  # Tool-call preamble is not a final answer.
    assert [call.id for call in result.tool_calls] == ["one", "two"]
    assert result.tool_calls[0].arguments == {"jd_text": "Intern\nPython"}
    assert result.tool_calls[1].arguments["resume_text"] == "Python 项目"
    request = sdk.requests[0]
    assert request["tool_choice"] == "auto"
    assert request["tools"] == [{"type": "function", "function": {
        "name": tool.name, "description": tool.description, "parameters": tool.parameters,
    }} for tool in tools]
    request["tools"][0]["function"]["parameters"].clear()
    assert tools[0].parameters  # SDK cannot mutate registry schema snapshots.


@pytest.mark.parametrize("success", [True, False])
def test_assistant_calls_and_success_or_error_results_round_trip(success):
    tool_result = ToolResult(
        tool_name="parse_job", success=success,
        data={"title": "实习生"} if success else None,
        error=None if success else ToolError(code="invalid_arguments", message="jd_text: missing"),
    )
    messages = [
        Message(role="user", content="task"),
        Message(role="assistant", tool_calls=[ToolCall(id="exact-id", name="parse_job", arguments={"jd_text": "实习生"})]),
        Message(role="tool", tool_call_id="exact-id", tool_result=tool_result),
        Message(role="assistant", content="previous final text"),
        Message(role="user", content="follow up"),
    ]
    sdk = FakeSDK([completion()])
    DeepSeekLLMClient(sdk_client=sdk).complete(messages, [])
    sent = sdk.requests[0]["messages"]
    assert sent[1]["content"] is None
    assert sent[1]["tool_calls"][0]["id"] == sent[2]["tool_call_id"] == "exact-id"
    assert sent[1]["tool_calls"][0]["type"] == "function"
    assert json.loads(sent[1]["tool_calls"][0]["function"]["arguments"]) == {"jd_text": "实习生"}
    assert json.loads(sent[2]["content"]) == tool_result.model_dump()
    assert sent[3] == {"role": "assistant", "content": "previous final text"}


def test_agent_multiround_batch_and_recoverable_errors_with_sdk_responses():
    sdk = FakeSDK([
        completion(None, calls=[tool_call("bad", arguments='{"jd_text":123}'), tool_call("unknown", "not_registered", '{}')]),
        completion(None, calls=[tool_call("fixed"), tool_call("evidence", "find_evidence", '{"resume_text":"Python project","skills":["Python"]}')]),
        completion("模型根据工具结果作答"),
    ])
    client = DeepSeekLLMClient(sdk_client=sdk)
    result = Agent(client, create_tool_registry(), max_steps=3).run("task")
    assert result.status == "completed"
    assert result.steps == client.request_count == 3
    second = sdk.requests[1]["messages"]
    assert [item["tool_call_id"] for item in second if item["role"] == "tool"] == ["bad", "unknown"]
    assert [json.loads(item["content"])["error"]["code"] for item in second if item["role"] == "tool"] == [
        "invalid_arguments", "unknown_tool",
    ]
    third = sdk.requests[2]["messages"]
    results = [item for item in third if item["role"] == "tool"]
    assert [item["tool_call_id"] for item in results] == ["bad", "unknown", "fixed", "evidence"]
    assert json.loads(results[2]["content"])["data"]["required_skills"] == ["Python"]
    assert json.loads(results[3]["content"])["data"][0]["found"] is True


@pytest.mark.parametrize("arguments", [
    "not json", '{"jd_text":', "[]", "null", '"text"', "123",
    '{"x":NaN}', '{"x":Infinity}', '{"x":1e999}', '{"x":1,"x":2}',
    {"jd_text": "not serialized"}, b'{}',
])
def test_invalid_tool_json_is_rejected_without_echoing_it(arguments):
    raw = SimpleNamespace(choices=[SimpleNamespace(
        finish_reason="tool_calls",
        message=SimpleNamespace(role="assistant", content=None, tool_calls=[SimpleNamespace(
            id="job", type="function", function=SimpleNamespace(name="parse_job", arguments=arguments),
        )]),
    )])
    client = DeepSeekLLMClient(sdk_client=FakeSDK([raw]))
    with pytest.raises(DeepSeekClientError) as caught:
        client.complete([Message(role="user", content="task")], [])
    assert caught.value.code == client.last_error_code == "invalid_tool_arguments"
    assert str(caught.value) == "DeepSeek tool arguments must be a valid JSON object."
    assert client.request_count == 1


@pytest.mark.parametrize("response, code", [
    (None, "invalid_response"),
    (SimpleNamespace(choices=[]), "invalid_response"),
    (completion("partial", finish_reason="length"), "response_truncated"),
    (completion(None, calls=[tool_call()], finish_reason="length"), "response_truncated"),
    (completion("", finish_reason="stop"), "invalid_response"),
    (completion(None), "invalid_response"),
    (completion("refused", finish_reason="content_filter"), "invalid_response"),
    (completion(None, calls=[tool_call()], finish_reason="stop"), "invalid_response"),
    (completion("text", finish_reason="tool_calls"), "invalid_response"),
    (completion(None, calls=[tool_call("same"), tool_call("same")]), "invalid_response"),
    (completion(None, calls=[tool_call("")]), "invalid_response"),
    (completion(None, calls=[tool_call(name=" ")]), "invalid_response"),
])
def test_abnormal_responses_stop_safely(response, code):
    client = DeepSeekLLMClient(sdk_client=FakeSDK([response]))
    with pytest.raises(DeepSeekClientError) as caught:
        client.complete([Message(role="user", content="task")], [])
    assert caught.value.code == client.last_error_code == code


def test_unexpected_thinking_response_is_not_silently_dropped():
    response = completion("done")
    response.choices[0].message.reasoning_content = "private reasoning"
    client = DeepSeekLLMClient(sdk_client=FakeSDK([response]))
    with pytest.raises(DeepSeekClientError, match="unsupported"):
        client.complete([Message(role="user", content="task")], [])


@pytest.mark.parametrize("failure, code", [
    (APITimeoutError(request=httpx.Request("POST", "https://api.deepseek.com")), "timeout"),
    (APIConnectionError(message="SYNTHETIC_PRIVATE_KEY", request=httpx.Request("POST", "https://api.deepseek.com")), "connection_error"),
    (RateLimitError("SYNTHETIC_PRIVATE_KEY", response=httpx.Response(429, request=httpx.Request("POST", "https://api.deepseek.com")), body=None), "api_error"),
    (RuntimeError("SYNTHETIC_PRIVATE_KEY"), "sdk_error"),
])
def test_api_errors_are_typed_redacted_and_not_retried(failure, code, capsys, caplog):
    sdk = FakeSDK([failure, completion("must not run")])
    client = DeepSeekLLMClient(sdk_client=sdk)
    result = Agent(client, create_tool_registry()).run("task")
    assert result.status == "model_error"
    assert result.error_code == "model_exception"  # Existing Agent interface stays stable.
    assert client.last_error_code == code
    assert client.request_count == len(sdk.requests) == 1
    assert "SYNTHETIC_PRIVATE_KEY" not in result.model_dump_json()
    assert capsys.readouterr().out == ""
    assert caplog.text == ""


def test_malformed_tool_json_stops_agent_without_executing_any_tool(monkeypatch):
    registry = create_tool_registry()
    execute = Mock(side_effect=AssertionError("No tool must execute"))
    monkeypatch.setattr(registry, "execute", execute)
    sdk = FakeSDK([completion(None, calls=[tool_call(arguments="PRIVATE_NOT_JSON")])])
    client = DeepSeekLLMClient(sdk_client=sdk)
    result = Agent(client, registry).run("task")
    assert result.status == "model_error"
    assert client.last_error_code == "invalid_tool_arguments"
    assert "PRIVATE_NOT_JSON" not in result.model_dump_json()
    execute.assert_not_called()


def test_call_budget_counts_attempts_and_blocks_before_sdk_call():
    sdk = FakeSDK([RuntimeError("failure"), completion()])
    client = DeepSeekLLMClient(sdk_client=sdk, max_calls=1)
    messages = [Message(role="user", content="task")]
    with pytest.raises(DeepSeekClientError) as first:
        client.complete(messages, [])
    assert first.value.code == "sdk_error"
    with pytest.raises(DeepSeekClientError) as second:
        client.complete(messages, [])
    assert second.value.code == "call_limit"
    assert client.request_count == len(sdk.requests) == 1


def test_non_json_outgoing_arguments_do_not_consume_budget_or_send():
    sdk = FakeSDK([])
    client = DeepSeekLLMClient(sdk_client=sdk)
    messages = [Message(role="assistant", tool_calls=[
        ToolCall(id="x", name="parse_job", arguments={"bad": object()}),
    ])]
    with pytest.raises(DeepSeekClientError) as caught:
        client.complete(messages, [])
    assert caught.value.code == "invalid_request"
    assert client.request_count == 0
    assert sdk.requests == []


def test_sdk_factory_uses_only_deepseek_key_fixed_endpoint_and_no_retries(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "synthetic-test-only-key")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-be-used")
    sdk = FakeSDK([])
    factory = Mock(return_value=sdk)
    monkeypatch.setattr("src.deepseek.OpenAI", factory)
    client = DeepSeekLLMClient(timeout=9)
    factory.assert_called_once_with(
        api_key="synthetic-test-only-key", base_url=BASE_URL, timeout=9, max_retries=0,
    )
    assert "synthetic-test-only-key" not in repr(client)


@pytest.mark.parametrize("key", [None, "", " \t"])
def test_missing_key_fails_before_sdk_creation(monkeypatch, key):
    if key is None:
        monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    else:
        monkeypatch.setenv("DEEPSEEK_API_KEY", key)
    factory = Mock()
    monkeypatch.setattr("src.deepseek.OpenAI", factory)
    with pytest.raises(DeepSeekClientError) as caught:
        DeepSeekLLMClient()
    assert caught.value.code == "configuration_error"
    factory.assert_not_called()


@pytest.mark.parametrize("configuration", [
    {"max_calls": 0}, {"max_calls": True}, {"max_tokens": 0}, {"max_tokens": "512"},
    {"timeout": 0}, {"timeout": True}, {"timeout": float("nan")}, {"timeout": float("inf")},
    {"model": " "},
])
def test_invalid_configuration_is_rejected(configuration):
    with pytest.raises(DeepSeekClientError) as caught:
        DeepSeekLLMClient(sdk_client=FakeSDK([]), **configuration)
    assert caught.value.code == "configuration_error"


def test_real_demo_requires_explicit_run_before_constructing_client(monkeypatch, capsys):
    from examples import demo_deepseek_agent as demo

    factory = Mock(side_effect=AssertionError("Client must not be created"))
    monkeypatch.setattr(demo, "DeepSeekLLMClient", factory)
    with pytest.raises(SystemExit) as caught:
        demo.main([])
    assert caught.value.code == 2
    factory.assert_not_called()
    assert "--run" in capsys.readouterr().err


def test_real_demo_flow_uses_only_fake_sdk_in_pytest(monkeypatch, capsys):
    from examples import demo_deepseek_agent as demo

    sdk = FakeSDK([completion(None, calls=[tool_call()]), completion("模拟最终回答")])
    factory = Mock(side_effect=lambda **kwargs: DeepSeekLLMClient(sdk_client=sdk, **kwargs))
    monkeypatch.setattr(demo, "DeepSeekLLMClient", factory)
    assert demo.main(["--run", "--max-calls", "2", "--max-tokens", "256"]) == 0
    assert len(sdk.requests) == 2
    assert [tool["function"]["name"] for tool in sdk.requests[0]["tools"]] == ["parse_job"]
    assert json.loads(sdk.requests[1]["messages"][-1]["content"])["success"]
    assert sdk.closed
    output = capsys.readouterr().out
    assert "API 请求次数：2/2" in output
    assert "终止状态：completed" in output


def test_demo_cli_rejects_limits_larger_than_its_cap(monkeypatch):
    from examples import demo_deepseek_agent as demo

    factory = Mock(side_effect=AssertionError("Client must not be created"))
    monkeypatch.setattr(demo, "DeepSeekLLMClient", factory)
    with pytest.raises(SystemExit):
        demo.main(["--run", "--max-calls", "100"])
    with pytest.raises(SystemExit):
        demo.main(["--run", "--max-tokens", "10000"])
    factory.assert_not_called()
