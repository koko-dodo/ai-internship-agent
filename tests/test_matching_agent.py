import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest
from openai.types.chat import ChatCompletion

from src.agent import Agent
from src.deepseek import DeepSeekLLMClient
from src.llm import LLMResponse, MockLLMClient, ToolCall
from src.matching import EvidenceBasedMatcher, create_matching_registry
from src.schemas import EvidenceMatchReport


JOB = {"title": "AI Intern", "company": "Example", "required_skills": ["Python", "SQL"], "preferred_skills": ["Docker"]}
RESUME = "Built a Python project.\n\nCompleted SQL basics."
EVALUATION = {"assessments": [
    {"skill": "Python", "status": "supported", "quotes": ["Built a Python project."], "reasoning": "有项目原文"},
    {"skill": "SQL", "status": "partial", "quotes": ["Completed SQL basics."], "reasoning": "仅基础学习"},
    {"skill": "Docker", "status": "not_found", "quotes": [], "reasoning": "当前简历没有足够证据"},
]}


def script():
    return [
        LLMResponse(tool_calls=[ToolCall(id="match-1", name="match_resume_to_job", arguments={})]),
        LLMResponse(final_answer=json.dumps(JOB)),
        LLMResponse(final_answer=json.dumps(EVALUATION)),
        LLMResponse(final_answer="This untrusted final text claims a score of 100."),
    ]


def matcher_for(tmp_path, client):
    path = tmp_path / "resume.md"
    path.write_text(RESUME, encoding="utf-8")
    return EvidenceBasedMatcher(client, str(path), "Original JD", allowed_directory=tmp_path)


def test_end_to_end_agent_tool_and_semantic_calls_with_one_shared_mock(tmp_path, caplog, capsys):
    client = MockLLMClient(script())
    result = Agent(client, create_matching_registry(matcher_for(tmp_path, client)), max_steps=2).run("Match task")
    assert result.status == "completed"
    assert result.steps == 2
    assert len(client.requests) == 4
    message = result.messages[2]
    assert message.tool_call_id == "match-1"
    assert message.tool_result.success
    report = EvidenceMatchReport.model_validate(message.tool_result.data)
    assert report.score.score == 60
    assert [item.status for item in report.skills] == ["supported", "partial", "not_found"]
    assert client.requests[-1].messages[-1].tool_result.data["score"]["score"] == 60
    assert "Built a Python" not in "\n".join(event.model_dump_json() for event in result.trace)
    assert caplog.text == capsys.readouterr().out == ""


def test_matching_tool_cannot_replace_bound_file_jd_or_score(tmp_path):
    client = MockLLMClient([])
    registry = create_matching_registry(matcher_for(tmp_path, client))
    assert registry.get_tool_schemas()[0].parameters["properties"] == {}
    for arguments in [{"file_path": "/elsewhere"}, {"jd_text": "Fake JD"}, {"score": 100}]:
        result = registry.execute("match_resume_to_job", arguments)
        assert result.error.code == "invalid_arguments"
    assert client.requests == []


def test_model_hallucinated_quote_reaches_report_only_as_uncertain(tmp_path):
    responses = script()
    hallucinated = {"assessments": [
        {"skill": "Python", "status": "supported", "quotes": ["Fabricated production service"], "reasoning": "Strong match"},
    ]}
    responses[2] = LLMResponse(final_answer=json.dumps(hallucinated))
    client = MockLLMClient(responses)
    result = Agent(client, create_matching_registry(matcher_for(tmp_path, client))).run("task")
    report = result.messages[2].tool_result.data
    assert result.status == "completed"
    assert report["score"]["score"] == 0
    assert all(item["status"] == "uncertain" for item in report["skills"])
    assert "Fabricated production" not in json.dumps(report)


def test_nested_model_failure_is_fatal_tool_error_without_leaking_payload(tmp_path):
    client = MockLLMClient([script()[0], RuntimeError("PRIVATE_PROVIDER_PAYLOAD")])
    result = Agent(client, create_matching_registry(matcher_for(tmp_path, client))).run("task")
    assert result.status == "tool_error"
    assert result.error_code == "execution_error"
    assert len(client.requests) == 2
    assert "PRIVATE_PROVIDER" not in result.model_dump_json()


@pytest.mark.parametrize("kind, code", [("missing", "file_not_found"), ("outside", "access_denied")])
def test_bound_matching_file_error_stops_agent_before_semantic_requests(tmp_path, kind, code):
    allowed = tmp_path / "allowed"
    allowed.mkdir()
    path = (allowed if kind == "missing" else tmp_path) / "resume.txt"
    client = MockLLMClient([script()[0]])
    matcher = EvidenceBasedMatcher(client, str(path), "Intern", allowed_directory=allowed)
    result = Agent(client, create_matching_registry(matcher)).run("Match task")
    assert result.status == "tool_error"
    assert result.error_code == code
    assert len(client.requests) == 1


def sdk_completion(response):
    message = {"role": "assistant", "content": response.final_answer}
    if response.tool_calls:
        message["tool_calls"] = [{"id": call.id, "type": "function", "function": {
            "name": call.name, "arguments": json.dumps(call.arguments),
        }} for call in response.tool_calls]
    return ChatCompletion.model_validate({
        "id": "sdk-test", "created": 0, "object": "chat.completion", "model": "fake-model",
        "choices": [{"index": 0, "message": message, "finish_reason": "tool_calls" if response.tool_calls else "stop"}],
    })


def fake_sdk(responses):
    return SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=Mock(side_effect=[sdk_completion(item) for item in responses]))),
        close=Mock(),
    )


def test_deepseek_adapter_runs_matching_end_to_end_with_offline_sdk(tmp_path):
    sdk = fake_sdk(script())
    client = DeepSeekLLMClient(sdk_client=sdk, max_calls=4, max_tokens=2048)
    result = Agent(client, create_matching_registry(matcher_for(tmp_path, client)), max_steps=2).run("task")
    assert result.status == "completed"
    assert client.request_count == sdk.chat.completions.create.call_count == 4
    requests = [call.kwargs for call in sdk.chat.completions.create.call_args_list]
    assert requests[0]["tools"][0]["function"]["name"] == "match_resume_to_job"
    assert "tools" not in requests[1] and "tools" not in requests[2]
    tool_result = requests[3]["messages"][-1]
    assert tool_result["tool_call_id"] == "match-1"
    assert json.loads(tool_result["content"])["data"]["score"]["score"] == 60


def test_shared_deepseek_budget_also_limits_nested_semantic_calls(tmp_path):
    sdk = fake_sdk(script())
    client = DeepSeekLLMClient(sdk_client=sdk, max_calls=2)
    result = Agent(client, create_matching_registry(matcher_for(tmp_path, client))).run("task")
    assert result.status == "tool_error"
    assert client.last_error_code == "call_limit"
    assert client.request_count == sdk.chat.completions.create.call_count == 2


def test_matching_demo_requires_explicit_opt_in(monkeypatch):
    from examples import demo_matching_agent as demo

    factory = Mock(side_effect=AssertionError("Client must not be constructed"))
    monkeypatch.setattr(demo, "DeepSeekLLMClient", factory)
    with pytest.raises(SystemExit) as caught:
        demo.main([])
    assert caught.value.code == 2
    factory.assert_not_called()


def test_matching_demo_shows_verified_report_not_assistant_claims(tmp_path, monkeypatch, capsys):
    from examples import demo_matching_agent as demo

    path = tmp_path / "resume.md"
    path.write_text(RESUME, encoding="utf-8")
    jd_path = tmp_path / "job.txt"
    jd_path.write_text("Original JD", encoding="utf-8")
    monkeypatch.setattr(demo, "EXAMPLES", tmp_path)
    sdk = fake_sdk(script())
    monkeypatch.setattr(demo, "DeepSeekLLMClient", lambda **kwargs: DeepSeekLLMClient(sdk_client=sdk, **kwargs))
    assert demo.main(["--run", "--resume", str(path), "--jd", str(jd_path)]) == 0
    output = capsys.readouterr().out
    assert '"score": 60.0' in output
    assert "untrusted final text" not in output
    assert "API 请求次数（含工具内语义请求）：4/6" in output
    assert sdk.close.called


def test_demo_does_not_accept_final_answer_without_report(monkeypatch, capsys):
    from examples import demo_matching_agent as demo

    sdk = fake_sdk([LLMResponse(final_answer="Fake 100-point report")])
    monkeypatch.setattr(demo, "DeepSeekLLMClient", lambda **kwargs: DeepSeekLLMClient(sdk_client=sdk, **kwargs))
    assert demo.main(["--run"]) == 1
    assert "Fake 100" not in capsys.readouterr().out
    assert sdk.close.called


def test_demo_rejects_outside_jd_before_constructing_api_client(tmp_path, monkeypatch):
    from examples import demo_matching_agent as demo

    outside = tmp_path / "private.md"
    outside.write_text("Private", encoding="utf-8")
    factory = Mock(side_effect=AssertionError("No client may be created"))
    monkeypatch.setattr(demo, "DeepSeekLLMClient", factory)
    assert demo.main(["--run", "--jd", str(outside)]) == 1
    factory.assert_not_called()
