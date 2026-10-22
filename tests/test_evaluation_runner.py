import json
from types import SimpleNamespace

import pytest

from evaluation.clients import ObservedLLM, RequestBudget, ScriptedLLM, UsageSDK
from evaluation.dataset import load_dataset
from evaluation.methods import run_method
from evaluation.report import build_report, dumps, markdown, write_report
from evaluation.run import main, run_suite
from src.autonomy import LLMBudgetExceeded


@pytest.fixture(scope="module")
def report():
    return run_suite(load_dataset())


def get_row(report, case_id, method):
    return next(row for row in report["runs"] if row["run"]["case_id"] == case_id and row["run"]["method"] == method)


def test_all_three_methods_share_inputs_and_multi_step_budgets(report):
    assert len(report["runs"]) == 36
    for case_id in [f"{i:02}" for i in range(1, 13)]:
        rows = [get_row(report, case_id, method)["run"] for method in ["single", "fixed", "agent"]]
        assert len({run["input_fingerprint"] for run in rows}) == 1
        assert rows[1]["authorized_sources"] == rows[2]["authorized_sources"]
        assert rows[1]["budgets"] == rows[2]["budgets"]
        assert rows[0]["authorized_sources"] == []
        assert rows[0]["cost"]["llm_requests"] == 1
    assert all(pair["same_inputs_grants_budgets"] and pair["same_initial_states"] and pair["same_initial_checkpoint"]
               for pair in report["policy_ablation"])


def test_single_keeps_hallucinated_status_score_and_raw_text(report):
    row = get_row(report, "09", "single")
    raw = json.loads(row["run"]["raw_model_output"])
    assert raw["assessments"][0]["status"] == row["run"]["predictions"][0]["status"] == "supported"
    assert raw["model_score"] == row["run"]["score"] == 88
    assert row["run"]["citations_verified_by_method"] is False
    assert row["metrics"]["evidence_validity"] == 0
    agent = get_row(report, "09", "agent")["run"]
    assert agent["predictions"][0]["status"] == "uncertain" and agent["score"] == 0


def test_fixed_really_searches_same_granted_data_and_differs_only_in_policy(report):
    fixed = get_row(report, "02", "fixed")["run"]
    agent = get_row(report, "02", "agent")["run"]
    assert fixed["predictions"] == agent["predictions"]
    assert fixed["initial_states"] == agent["initial_states"]
    assert len(fixed["retrievals"]) == 2 and len(agent["retrievals"]) == 1
    assert fixed["retrievals"][0]["source"].endswith("a_notes.md")
    assert fixed["retrievals"][1]["source"] == agent["retrievals"][0]["source"]
    assert fixed["cost"]["llm_requests"] == 3  # Two initial semantic calls plus evidence review.
    assert agent["cost"]["llm_requests"] == 5  # Same reviews plus SEARCH / FINISH decisions.


def test_semantic_prompts_are_identical_and_contain_no_gold():
    clients = {}
    class Spy(ScriptedLLM):
        def __init__(self, case_id):
            super().__init__(case_id)
            self.requests = []
        def complete(self, messages, tools):
            self.requests.append((messages[-1].content, tools))
            return super().complete(messages, tools)
    def factory(case, method, cap):
        client = clients[method] = Spy(case.id)
        return ObservedLLM(client)
    dataset = load_dataset()
    run_suite(dataset, case_ids=["02"], client_factory=factory)
    assert clients["fixed"].requests[:2] == clients["agent"].requests[:2]
    gold_rationale = dataset.cases[1].gold[0].rationale
    assert all(gold_rationale not in prompt and tools == [] for client in clients.values() for prompt, tools in client.requests)
    baseline_data = json.loads(clients["single"].requests[0][0].split("\n")[-1])["data"]
    assert set(baseline_data) == {"resume_text", "jd_text"}
    assert "I implemented RAG retrieval" not in baseline_data["resume_text"]


@pytest.mark.parametrize("method", ["fixed", "agent"])
def test_no_reply_preserves_waiting_but_allowed_reply_resumes_without_evidence_credit(report, method):
    waiting = get_row(report, "07", method)["run"]
    assert waiting["status"] == "waiting_for_user"
    assert waiting["interactions"][0]["reply"] is None
    replied = get_row(report, "08", method)["run"]
    assert replied["status"] == "finished" and replied["score"] == 0
    assert replied["predictions"][0]["status"] == "not_found"
    assert replied["interactions"][0]["reply"] == load_dataset().cases[7].user_reply
    assert replied["interactions"][0]["verified"] is False
    assert replied["predictions"][0]["citations"] == []


@pytest.mark.parametrize("case_id,status,fault", [("10", "permission_denied", "access_denied"), ("11", "tool_error", "io_error")])
def test_shared_synthetic_faults_are_explicit_not_hidden_method_advantages(report, case_id, status, fault):
    for method in ["fixed", "agent"]:
        run = get_row(report, case_id, method)["run"]
        assert run["status"] == status and run["injected_fault"] == fault
        assert len(run["retrievals"]) == 1 and run["retrievals"][0]["candidates"] == []
        assert run["retrievals"][0]["error_code"] == fault


def test_invalid_decision_recovery_preserves_actual_agent_trace(report):
    row = get_row(report, "12", "agent")
    assert row["run"]["status"] == "finished"
    assert row["metrics"]["invalid_actions"] == 1
    assert row["run"]["predictions"][0]["status"] == "supported"
    assert any(event["error_code"] == "invalid_target" for event in row["run"]["trace"])


def test_framework_outputs_are_labeled_mock_and_make_no_superiority_claim(report):
    assert report["mode"] == "mock" and "not real model accuracy" in report["interpretation"]
    assert all(stats["token_usage"]["total_tokens"] is None for stats in report["summary"].values())
    assert report["summary"]["fixed"]["skill_status_accuracy"] == report["summary"]["agent"]["skill_status_accuracy"]
    assert report["summary"]["fixed"]["llm_requests"] < report["summary"]["agent"]["llm_requests"]
    assert len(report["by_scenario"]) == 12


def test_reports_reproduce_semantics_with_measured_latency_and_stable_serialization(report, tmp_path):
    repeat = run_suite(load_dataset())
    assert report["semantic_fingerprint"] == repeat["semantic_fingerprint"]
    assert all(row["run"]["latency_seconds"] > 0 for row in repeat["runs"])
    write_report(report, tmp_path)
    before = (tmp_path / "mock.json").read_bytes(), (tmp_path / "mock.md").read_bytes()
    write_report(report, tmp_path)
    assert before == ((tmp_path / "mock.json").read_bytes(), (tmp_path / "mock.md").read_bytes())
    assert json.loads(before[0]) == report
    assert dumps(report).encode() == before[0]
    text = markdown(report)
    assert "unavailable" in text and "Scenario groups" in text and "Policy ablation" in text


def test_report_rejects_mixed_modes_or_fake_api_usage():
    dataset = load_dataset()
    case = dataset.cases[0]
    run = run_method(case, "single", ObservedLLM(ScriptedLLM(case.id)))
    other = run.model_copy(deep=True, update={"mode": "real", "method": "agent"})
    with pytest.raises(ValueError, match="separate reports"):
        build_report(dataset, [run, other])
    run.cost["token_usage"]["total_tokens"] = 100
    with pytest.raises(ValueError, match="Mock runs"):
        build_report(dataset, [run])


@pytest.mark.parametrize("kwargs", [
    {"mode": "real"}, {"mode": "real", "case_ids": ["01"]},
    {"mode": "real", "allow_paid": True},
    {"mode": "real", "allow_paid": True, "case_ids": ["01", "02", "03"]},
    {"mode": "real", "allow_paid": True, "case_ids": ["01"], "max_total_requests": 1},
    {"mode": "real", "allow_paid": True, "case_ids": ["01", "02"], "max_total_requests": 25},
    {"mode": "real", "allow_paid": True, "case_ids": ["01"], "max_total_requests": 51},
    {"allow_paid": True}, {"case_ids": ["not-a-case"]}, {"case_ids": ["01", "01"]},
])
def test_paid_guard_and_input_checks_run_before_any_client_creation(kwargs):
    calls = []
    def forbidden_factory(*args):
        calls.append(args)
        raise AssertionError("Must not create a client")
    with pytest.raises(ValueError):
        run_suite(load_dataset(), client_factory=forbidden_factory, **kwargs)
    assert calls == []


def test_scripted_outputs_cannot_be_labeled_real_even_with_opt_in():
    with pytest.raises(ValueError, match="cannot be labeled real"):
        run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["01"],
                  client_factory=lambda case, method, cap: ObservedLLM(ScriptedLLM(case.id)))


def test_default_cli_never_constructs_live_client(tmp_path, monkeypatch, capsys):
    import evaluation.run as runner
    def forbidden(*args):
        raise AssertionError("No live client allowed")
    monkeypatch.setattr(runner, "live_client", forbidden)
    assert main(["--case", "01", "--output", str(tmp_path)]) == 0
    assert (tmp_path / "mock.json").exists() and not (tmp_path / "real.json").exists()
    assert "SCRIPTED FRAMEWORK VALIDATION ONLY" in capsys.readouterr().out


def test_actual_usage_is_observed_at_sdk_boundary_and_failed_calls_remain_unavailable():
    from src.deepseek import DeepSeekClientError, DeepSeekLLMClient
    from src.llm import Message
    count = 0
    def create(**kwargs):
        nonlocal count
        count += 1
        if count == 2:
            raise RuntimeError("SECRET-NOT-LOGGED")
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=4, completion_tokens=2, total_tokens=6),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(role="assistant", content="OK", tool_calls=[]))])
    sdk = UsageSDK(SimpleNamespace(chat=SimpleNamespace(completions=SimpleNamespace(create=create))))
    adapter = DeepSeekLLMClient(sdk_client=sdk, max_calls=2)
    observed = ObservedLLM(adapter, usage_source=sdk)
    observed.complete([Message(role="user", content="fixture")], [])
    assert observed.cost()["token_usage"] == {"prompt_tokens": 4, "completion_tokens": 2, "total_tokens": 6}
    with pytest.raises(DeepSeekClientError):
        observed.complete([Message(role="user", content="fixture")], [])
    assert observed.cost()["llm_requests"] == observed.cost()["api_requests"] == 2
    assert observed.cost()["usage_requests_available"] == 1
    assert observed.cost()["token_usage"]["total_tokens"] is None


def test_request_budget_is_hard_and_failure_attempts_count():
    client = ObservedLLM(ScriptedLLM("01"), global_budget=RequestBudget(1))
    with pytest.raises(IndexError):  # Empty history intentionally fails after consuming an attempt.
        client.complete([], [])
    with pytest.raises(LLMBudgetExceeded):
        client.complete([], [])
    assert client.requests == 1


def test_multi_step_caps_include_initial_semantic_calls():
    case = load_dataset().cases[1]
    for method in ["fixed", "agent"]:
        run = run_method(case, method, ObservedLLM(ScriptedLLM(case.id)), max_requests=2)
        assert run.status == "budget_exhausted" and run.cost["llm_requests"] == 2
        assert run.retrievals == []


@pytest.mark.parametrize("answer", ["{broken JSON", '{"assessments": [{"skill": "Python", "status": "excellent"}]}'])
def test_single_invalid_output_is_preserved_not_repaired(answer):
    from src.llm import LLMResponse, MockLLMClient
    case = load_dataset().cases[0]
    run = run_method(case, "single", ObservedLLM(MockLLMClient([LLMResponse(final_answer=answer)])))
    assert run.status == "model_error" and run.raw_model_output == answer
    assert run.cost["llm_requests"] == 1 and run.predictions == []


def test_single_unexpected_tool_request_is_retained_but_never_executed():
    from src.llm import LLMResponse, MockLLMClient, ToolCall
    response = LLMResponse(tool_calls=[ToolCall(id="call1", name="read_resume", arguments={"file_path": "forbidden.md"})])
    case = load_dataset().cases[0]
    run = run_method(case, "single", ObservedLLM(MockLLMClient([response])))
    assert run.status == "model_error" and json.loads(run.raw_model_output)["tool_calls"][0]["id"] == "call1"
    assert run.retrievals == [] and run.trace == [] and run.cost["llm_requests"] == 1


def test_single_model_exception_is_sanitized_and_counted():
    from src.llm import MockLLMClient
    case = load_dataset().cases[0]
    run = run_method(case, "single", ObservedLLM(MockLLMClient([RuntimeError("PRIVATE-ERROR")])))
    assert run.status == "model_error" and run.cost["llm_requests"] == 1
    assert "PRIVATE-ERROR" not in run.model_dump_json()
