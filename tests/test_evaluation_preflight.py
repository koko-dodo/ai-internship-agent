"""Real-adapter wiring verified with an offline SDK stub, never live requests."""

import json
from types import SimpleNamespace

import pytest

import evaluation.run as runner
from evaluation.clients import ObservedLLM, ScriptedLLM, UsageSDK
from evaluation.dataset import load_dataset
from evaluation.methods import run_method
from evaluation.report import validate_report_output, write_report
from src.llm import LLMResponse, MockLLMClient


class OfflineSDK:
    """SDK-boundary test double; its results are not live model measurements."""

    def __init__(self, case_id):
        self.script = ScriptedLLM(case_id)
        self.requests, self.closed = [], False
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.requests.append(kwargs)
        message = SimpleNamespace(content=kwargs["messages"][-1]["content"])
        scripted = self.script.complete([message], [])
        return SimpleNamespace(usage=SimpleNamespace(prompt_tokens=5, completion_tokens=2, total_tokens=7),
            choices=[SimpleNamespace(finish_reason="stop", message=SimpleNamespace(
                role="assistant", content=scripted.final_answer, tool_calls=[]))])

    def close(self):
        self.closed = True


def sdk_factory(created):
    from src.deepseek import DeepSeekLLMClient
    def factory(case, method, cap):
        sdk = OfflineSDK(case.id)
        created.append((method, cap, sdk))
        observed_sdk = UsageSDK(sdk)
        return ObservedLLM(DeepSeekLLMClient(model="deepseek-flash", max_calls=cap, max_tokens=1024, sdk_client=observed_sdk),
                           usage_source=observed_sdk)
    return factory


@pytest.fixture(scope="module")
def sdk_report():
    created = []
    report = runner.run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["02"],
                              client_factory=sdk_factory(created))
    return report, created


def test_real_factory_constructs_deepseek_sdk_at_correct_endpoint_without_reading_credentials(monkeypatch):
    import openai
    from src.deepseek import BASE_URL, DeepSeekLLMClient
    constructed = []
    def factory(**kwargs):
        constructed.append(kwargs)
        return OfflineSDK("02")
    monkeypatch.setattr(openai, "OpenAI", factory)
    # No real environment variable/key lookup: replace only this module's os.
    monkeypatch.setattr(runner, "os", SimpleNamespace(environ={"DEEPSEEK_API_KEY": "offline-test-only"}))
    observed = runner.live_client("deepseek-flash", 12, runner.RequestBudget(25))
    assert type(observed.client) is DeepSeekLLMClient
    assert isinstance(observed.usage_source, UsageSDK)
    assert constructed[0]["base_url"] == BASE_URL == "https://api.deepseek.com"
    assert constructed[0]["max_retries"] == 0 and constructed[0]["timeout"] == 30
    assert observed.client.max_calls == 12 and observed.client.max_tokens == 1024
    assert observed.usage_source.sdk.requests == []
    observed.client.close()


def test_real_mode_rejects_generic_mock_not_just_scripted_llm():
    observed = ObservedLLM(MockLLMClient([LLMResponse(final_answer="must not run")]))
    with pytest.raises(ValueError, match="requires the configured DeepSeekLLMClient"):
        runner.run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["02"],
                         client_factory=lambda *_: observed)
    assert observed.requests == 0


def test_real_adapter_order_shared_frozen_inputs_caps_and_observed_usage(sdk_report):
    report, created = sdk_report
    assert [method for method, _, _ in created] == ["single", "fixed", "agent"]
    assert [cap for _, cap, _ in created] == [1, 12, 12]
    assert report["dataset_version"] == "gold-v1"
    assert report["request_plan"]["case_ids"] == ["02"]
    assert report["request_plan"]["method_order"] == ["single", "fixed", "agent"]
    assert report["request_plan"]["total_request_cap"] == report["request_plan"]["worst_case_request_reservation"] == 25
    assert len({row["run"]["input_fingerprint"] for row in report["runs"]}) == 1
    assert [event["method"] for event in report["execution_order"]] == ["single", "fixed", "agent"]
    assert [len(sdk.requests) for _, _, sdk in created] == [1, 3, 5]
    for row, (_, cap, sdk) in zip(report["runs"], created):
        run = row["run"]
        assert sdk.closed and run["cost"]["llm_requests"] == run["cost"]["api_requests"] == len(sdk.requests)
        assert run["cost"]["token_usage"]["total_tokens"] == 7 * len(sdk.requests)
        assert len(run["model_outputs"]) == len(sdk.requests)
        assert run["budgets"]["max_requests"] == cap
        assert all(request["model"] == "deepseek-flash" and request["max_tokens"] == 1024 for request in sdk.requests)
        assert all("messages" not in output and "prompt" not in output for output in run["model_outputs"])
    assert report["normal_access"]["controls"] == []  # Case 02 has no injected fault.


def test_raw_semantic_judgment_is_separate_from_verified_state():
    case = load_dataset().cases[8]
    run = run_method(case, "agent", ObservedLLM(ScriptedLLM(case.id)))
    raw = next(output for output in run.model_outputs if output["stage"] == "initial_assessment")
    assert json.loads(raw["response"]["final_answer"])["assessments"][0]["status"] == "supported"
    assert run.initial_states["Python"] == run.predictions[0].status == "uncertain"
    assert run.score == 0 and "prompts" not in run.model_dump()


def test_case02_no_reply_does_not_resume_or_invent_answer():
    class AskFirst(ScriptedLLM):
        def __init__(self):
            super().__init__("02")
            self.script["actions"] = [{"action": "ASK_USER", "skill": "RAG", "reason": "Clarify practice.",
                                       "question": "Can you provide your own complete RAG implementation details?"}]
    case = load_dataset().cases[1]
    assert case.user_reply is None
    run = run_method(case, "agent", ObservedLLM(AskFirst()))
    assert run.status == "waiting_for_user" and run.cost["llm_requests"] == 3
    assert run.interactions[0]["reply"] is None and run.interactions[0]["verified"] is False
    assert run.retrievals == [] and not any(event["event"] == "user_reply" for event in run.trace)


def test_sdk_failure_consumes_both_budgets_and_records_no_private_exception():
    from src.deepseek import DeepSeekLLMClient
    class BrokenSDK(OfflineSDK):
        def create(self, **kwargs):
            self.requests.append(kwargs)
            raise RuntimeError("PRIVATE-SDK-DETAIL")
    sdk = UsageSDK(BrokenSDK("02"))
    global_budget = runner.RequestBudget(1)
    observed = ObservedLLM(DeepSeekLLMClient(sdk_client=sdk, max_calls=1), usage_source=sdk, global_budget=global_budget)
    run = run_method(load_dataset().cases[1], "single", observed, mode="real", model="deepseek-flash")
    assert run.status == "model_error" and global_budget.used == 1
    assert run.cost["llm_requests"] == run.cost["api_requests"] == 1
    assert run.cost["token_usage"]["total_tokens"] is None
    assert run.model_outputs[0]["error_code"] == "model_exception"
    assert "PRIVATE-SDK-DETAIL" not in run.model_dump_json()


def test_global_cap_includes_all_methods_and_initialization():
    created = []
    report = runner.run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["02"],
                              max_requests=2, max_total_requests=5, client_factory=sdk_factory(created))
    assert sum(len(sdk.requests) for _, _, sdk in created) == 5
    assert [row["run"]["status"] for row in report["runs"]] == ["finished", "budget_exhausted", "budget_exhausted"]


def test_check_only_never_constructs_any_client_or_writes_reports(tmp_path, monkeypatch, capsys):
    def forbidden(*args, **kwargs):
        raise AssertionError("No client creation/execution in check-only mode")
    monkeypatch.setattr(runner, "live_client", forbidden)
    monkeypatch.setattr(runner, "run_suite", forbidden)
    output = tmp_path / "fresh"
    assert runner.main(["--mode", "real", "--allow-paid", "--case", "02", "--check-only",
                        "--max-requests", "12", "--max-total-requests", "25", "--output", str(output)]) == 0
    text = capsys.readouterr().out
    assert "no LLM/SDK client constructed" in text and '"total_request_cap": 25' in text
    assert not output.exists()


@pytest.mark.parametrize("collision", ["real.json", "real.md", "symlink", "directory-file"])
def test_output_collision_stops_before_paid_client_creation(tmp_path, monkeypatch, collision):
    output = tmp_path / "output"
    if collision == "directory-file":
        output.write_text("KEEP")
    else:
        output.mkdir()
        if collision == "symlink":
            protected = tmp_path / "mock.json"
            protected.write_text("KEEP")
            (output / "real.json").symlink_to(protected)
        else:
            (output / collision).write_text("KEEP")
    calls = []
    monkeypatch.setattr(runner, "live_client", lambda *args: calls.append(args))
    with pytest.raises(SystemExit) as error:
        runner.main(["--mode", "real", "--allow-paid", "--case", "02", "--output", str(output)])
    assert error.value.code == 2 and calls == []
    if collision in {"real.json", "real.md"}:
        assert (output / collision).read_text() == "KEEP"
    if collision == "symlink":
        assert protected.read_text() == "KEEP"


def test_real_reports_do_not_overwrite_mock_or_frozen_files_and_refuse_rerun(sdk_report, tmp_path):
    report, _ = sdk_report
    (tmp_path / "mock.json").write_text("PRESERVED-MOCK")
    (tmp_path / "cases.json").write_text("PRESERVED-GOLD")
    write_report(report, tmp_path)
    saved = (tmp_path / "real.json").read_bytes()
    with pytest.raises(ValueError, match="collision"):
        write_report(report, tmp_path)
    assert (tmp_path / "real.json").read_bytes() == saved
    assert (tmp_path / "mock.json").read_text() == "PRESERVED-MOCK"
    assert (tmp_path / "cases.json").read_text() == "PRESERVED-GOLD"


def test_output_directory_symlink_rejected(tmp_path):
    actual = tmp_path / "actual"
    actual.mkdir()
    alias = tmp_path / "alias"
    alias.symlink_to(actual, target_is_directory=True)
    with pytest.raises(ValueError, match="directory"):
        validate_report_output("real", alias)


@pytest.mark.parametrize("overrides", [{"model": "different-model"}, {"max_calls": 2},
                                      {"max_tokens": 512}, {"timeout": 60}])
def test_real_injected_adapter_cannot_silently_change_model_or_budget_settings(overrides):
    from src.deepseek import DeepSeekLLMClient
    sdk = UsageSDK(OfflineSDK("02"))
    settings = {"model": "deepseek-flash", "max_calls": 1, "max_tokens": 1024, "timeout": 30, **overrides}
    observed = ObservedLLM(DeepSeekLLMClient(sdk_client=sdk, **settings), usage_source=sdk)
    with pytest.raises(ValueError, match="configured DeepSeekLLMClient"):
        runner.run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["02"],
                         client_factory=lambda *_: observed)
    assert observed.requests == 0 and sdk.sdk.requests == []


def test_freeze_drift_during_run_stops_before_next_real_client(monkeypatch):
    verify = runner.verify_gold_freeze
    checks = 0
    def detect(dataset):
        nonlocal checks
        checks += 1
        if checks == 3:  # Suite validation, before Single, after Single.
            raise ValueError("simulated frozen-data drift")
        return verify(dataset)
    created = []
    monkeypatch.setattr(runner, "verify_gold_freeze", detect)
    with pytest.raises(ValueError, match="simulated frozen-data drift"):
        runner.run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["02"],
                         client_factory=sdk_factory(created))
    assert len(created) == 1 and created[0][2].closed
