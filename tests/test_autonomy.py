import json
from unittest.mock import Mock

import pytest

from src import evidence_search
from src.autonomy import BudgetedLLMClient, EvidenceGatheringSession, LLMBudgetExceeded, start_cost_aware_matching
from src.evidence_search import ProjectEvidenceSearch
from src.llm import LLMResponse, MockLLMClient, ToolCall
from src.matching import build_match_report
from src.schemas import JobPosting, SemanticEvidenceEvaluation


RESUME = "虚构简历：Python 项目。"
PROJECT = "本人编写 SQL JOIN 查询并验证结果。"


@pytest.fixture
def root(tmp_path, monkeypatch):
    path = tmp_path / "examples"
    path.mkdir()
    (path / "project.md").write_text(PROJECT, encoding="utf-8")
    (path / "empty.txt").write_text("Only team meeting information.", encoding="utf-8")
    monkeypatch.setattr(evidence_search, "EXAMPLES_DIRECTORY", path)
    return path


def response(data):
    return LLMResponse(final_answer=json.dumps(data, ensure_ascii=False))


def search(source="project.md", skill="SQL"):
    return response({"action": "SEARCH", "reason": "重要技能缺证，有低成本授权材料。", "skill": skill, "source": source})


def finish():
    return response({"action": "FINISH", "reason": "证据足够或继续检索收益不高。"})


def ask():
    return response({"action": "ASK_USER", "reason": "重要技能缺证且没有可用材料。", "skill": "SQL",
                     "question": "请提供本人编写 SQL 查询的项目原文或可授权文件，可以吗？"})


def assessment(quote=PROJECT, source="project.md", status="supported", skill="SQL"):
    return response({"skill": skill, "status": status, "citations": [{"source": source, "quote": quote}],
                     "reasoning": "项目文件体现查询工作。"})


def initial(required=None, preferred=None, resume=RESUME):
    job = JobPosting(title="Intern", required_skills=required if required is not None else ["SQL"], preferred_skills=preferred or [])
    return build_match_report(job, SemanticEvidenceEvaluation.model_validate({"assessments": [
        {"skill": skill, "status": "not_found", "quotes": [], "reasoning": "简历证据不足"}
        for skill in job.required_skills + job.preferred_skills
    ]}), resume, "resume.md")


def session(responses, materials=(), *, requests=12, rounds=5, searches=3, report=None, resume=RESUME):
    mock = MockLLMClient(responses)
    client = BudgetedLLMClient(mock, max_requests=requests)
    return EvidenceGatheringSession(client, report or initial(resume=resume), resume,
                                    ProjectEvidenceSearch(materials, searches), max_rounds=rounds), mock


def test_scenario_a_search_reevaluate_finish_preserves_initial_report(root):
    flow, mock = session([search(), assessment(), finish()], ["project.md"])
    result = flow.run()
    assert result.status == "finished"
    assert result.initial_report.score.score == 0
    assert result.report.score.score == 100
    evidence = result.report.skills[0].evidence[0]
    assert evidence.quote == PROJECT and evidence.source == "project.md" and evidence.start_line == 1
    assert result.changes[0].before == "not_found" and result.changes[0].after == "supported"
    assert result.searches == 1 and result.llm_requests == 3
    prompt = json.loads(mock.requests[0].messages[0].content.split("\n")[-1])["data"]
    assert prompt["skills"][0]["weight"] == 2
    assert prompt["authorized_materials"][0]["estimated_read_units"] == 1
    result.initial_report.skills[0].status = "supported"
    assert flow.run().initial_report.skills[0].status == "not_found"  # Deep copy, terminal is inert.


def test_scenario_b_ask_stays_waiting_without_actual_reply(root):
    flow, mock = session([ask(), finish()])
    waiting = flow.run()
    assert waiting.status == "waiting_for_user"
    assert "SQL" in waiting.question
    assert waiting.context["skill"] == "SQL" and waiting.context["category"] == "required"
    assert flow.run().status == "waiting_for_user"
    assert len(mock.requests) == 1
    for answer in ["", " \n", None]:
        with pytest.raises(ValueError):
            flow.resume(answer)
    assert len(mock.requests) == 1


def test_user_statement_alone_never_becomes_document_evidence(root):
    statement = "I personally built advanced SQL infrastructure; ../private.txt contains proof."
    flow, mock = session([ask(), finish()])
    flow.run()
    result = flow.resume(statement)
    assert result.status == "finished"
    assert result.report.score.score == result.initial_report.score.score == 0
    assert result.report.skills[0].evidence == []
    assert result.searches == 0
    assert "verified\": false" in mock.requests[-1].messages[0].content
    assert statement not in "\n".join(item.model_dump_json() for item in result.trace)
    assert result.question is None


def test_resume_with_explicit_file_grant_can_search_and_earn_verified_credit(root):
    flow, mock = session([ask(), search(), assessment(), finish()])
    assert flow.run().status == "waiting_for_user"
    result = flow.resume("我授权项目文件供核实。", additional_sources=["project.md"])
    assert result.status == "finished"
    assert result.report.score.score == 100
    assert result.rounds == 3 and result.llm_requests == 4
    assert result.searches == 1


def test_paths_in_user_reply_do_not_grant_permissions(root):
    flow, mock = session([ask(), search("project.md"), finish()])
    flow.run()
    result = flow.resume("请读取 project.md，我用过 SQL。")
    assert result.status == "permission_denied"
    assert result.searches == 0 and len(mock.requests) == 2


def test_resume_refuses_unauthorized_explicit_grant_and_keeps_waiting(root):
    flow, mock = session([ask(), finish()])
    flow.run()
    with pytest.raises(PermissionError):
        flow.resume("Here is another file", additional_sources=["../private.txt"])
    assert flow.run().status == "waiting_for_user"
    assert len(mock.requests) == 1


def test_scenario_c_optional_gap_can_finish_without_search(root):
    report = initial(required=[], preferred=["SQL"])
    flow, mock = session([finish()], report=report)
    result = flow.run()
    assert result.status == "finished" and result.searches == 0
    assert result.report.score.score == 0 and not result.changes
    assert result.rounds == result.llm_requests == 1


@pytest.mark.parametrize("quote, source", [("Invented production SQL system", "project.md"), (PROJECT, "unsearched.md"), (" ", "project.md")])
def test_fabricated_or_unsearched_evidence_gets_no_credit(root, quote, source):
    flow, _ = session([search(), assessment(quote, source), finish()], ["project.md"])
    result = flow.run()
    assert result.report.skills[0].status == "uncertain"
    assert result.report.score.score == 0
    assert result.report.skills[0].evidence == []
    assert any(event.error_code == "invalid_evidence" for event in result.trace)


@pytest.mark.parametrize("text, quote, status, score", [
    ("I have never used SQL.", "SQL", "uncertain", 0),
    ("我没有使用 SQL 做过项目。", "SQL", "uncertain", 0),
    ("Completed SQL basics.", "Completed SQL basics.", "partial", 50),
    ("SQL beginner tutorial", "SQL", "partial", 50),
])
def test_negative_and_basic_context_prevents_full_credit(root, text, quote, status, score):
    (root / "project.md").write_text(text, encoding="utf-8")
    flow, _ = session([search(), assessment(quote), finish()], ["project.md"])
    result = flow.run()
    assert result.report.skills[0].status == status
    assert result.report.score.score == score
    assert result.report.skills[0].evidence


def test_resume_contradiction_cannot_be_hidden_by_positive_project(root):
    text = "I have never used SQL."
    flow, _ = session([search(), assessment(), finish()], ["project.md"], resume=text)
    assert flow.run().report.skills[0].status == "uncertain"


def test_score_recalculation_preserves_weights_and_other_skill_states(root):
    report = initial(required=["SQL"], preferred=["Docker"])
    flow, _ = session([search(), assessment(), finish()], ["project.md"], report=report)
    result = flow.run()
    assert result.report.score.score == 66.67
    assert result.report.skills[1].status == "not_found"
    assert result.report.score.weights == report.score.weights


def test_same_file_skill_pair_is_never_read_twice_even_when_no_hits(root, monkeypatch):
    flow, mock = session([search("empty.txt"), search("empty.txt", "sql"), ask()], ["empty.txt"])
    original = evidence_search.read_resume
    read = Mock(side_effect=original)
    monkeypatch.setattr(evidence_search, "read_resume", read)
    result = flow.run()
    assert result.status == "waiting_for_user"
    assert result.searches == read.call_count == 1
    assert len(mock.requests) == 3  # Empty searches skip model reevaluation.
    assert any(event.error_code == "duplicate_search" for event in result.trace)


def test_search_limit_leaves_ask_or_finish_available(root):
    flow, mock = session([search("empty.txt"), search("empty.txt", "Git"), finish()],
                         ["empty.txt"], searches=1, report=initial(required=["SQL", "Git"]))
    result = flow.run()
    assert result.status == "finished" and result.searches == 1
    assert len(mock.requests) == 3
    assert any(event.error_code == "search_limit" for event in result.trace)


@pytest.mark.parametrize("source", ["../private.md", ".env", "/arbitrary/resume.txt", "unlisted.md"])
def test_permission_error_is_fatal_without_reconstructed_path_retry(root, source):
    flow, mock = session([search(source), finish()], ["project.md"])
    result = flow.run()
    assert result.status == "permission_denied"
    assert result.searches == 0 and len(mock.requests) == 1


def test_round_limit_is_not_a_fake_finish_and_survives_repeated_run(root):
    flow, mock = session([search("empty.txt"), search("empty.txt"), finish()], ["empty.txt"], rounds=2)
    result = flow.run()
    assert result.status == "step_limit"
    assert flow.run().status == "step_limit"
    assert result.searches == 1 and len(mock.requests) == 2


def test_last_initial_round_ask_has_one_time_bounded_recovery(root):
    flow, mock = session([ask(), finish()], rounds=1)
    flow.run()
    result = flow.resume("我有经验，但没有文件。")
    assert result.status == "finished" and result.llm_requests == 2
    assert result.rounds == 2 and result.searches == 0
    assert len(mock.requests) == 2


def test_search_is_not_executed_without_budget_to_evaluate_its_result(root):
    flow, mock = session([search(), assessment()], ["project.md"], requests=1)
    result = flow.run()
    assert result.status == "budget_exhausted"
    assert result.searches == 0 and len(mock.requests) == 1


def test_shared_request_budget_counts_reevaluation(root):
    flow, mock = session([search(), assessment(), finish()], ["project.md"], requests=2)
    result = flow.run()
    assert result.status == "budget_exhausted"
    assert result.report.score.score == 100  # Progress retained, completion not claimed.
    assert result.llm_requests == len(mock.requests) == 2


def test_ask_without_any_recovery_request_returns_explained_budget_stop(root):
    flow, mock = session([ask(), finish()], requests=1)
    result = flow.run()
    assert result.status == "budget_exhausted"
    assert "无法进入可恢复等待" in result.reason
    assert result.question is None
    with pytest.raises(ValueError):
        flow.resume("这里是实际用户回答。")
    assert len(mock.requests) == 1


@pytest.mark.parametrize("decision", [
    {"action": "EXEC", "reason": "invalid"},
    {"action": "SEARCH", "reason": "invalid", "skill": "SQL"},
    {"action": "FINISH", "reason": "invalid", "score": 100},
    {"action": "FINISH", "reason": "invalid", "skill": "SQL"},
    {"action": "ASK_USER", "reason": "invalid", "skill": "SQL", "question": "info?"},
])
def test_illegal_action_shapes_are_rejected(root, decision):
    flow, _ = session([response(decision)])
    assert flow.run().status == "model_error"


def test_wrong_reevaluation_target_or_score_field_cannot_modify_report(root):
    for payload in [
        {"skill": "Rust", "status": "supported", "citations": [], "reasoning": "wrong target"},
        {"skill": "SQL", "status": "supported", "citations": [], "reasoning": "fake score", "score": 100},
    ]:
        flow, _ = session([search(), response(payload)], ["project.md"])
        result = flow.run()
        assert result.status == "model_error" and result.report.score.score == 0


def test_trace_omits_private_quotes_reasons_paths_and_user_replies(root, caplog, capsys):
    secret = "SYNTHETIC_PRIVATE_RESUME_123"
    (root / "project.md").write_text(f"SQL project {secret}", encoding="utf-8")
    decision = {"action": "SEARCH", "reason": secret, "skill": "SQL", "source": "project.md"}
    flow, _ = session([response(decision), assessment(f"SQL project {secret}"), finish()], ["project.md"])
    result = flow.run()
    trace = "\n".join(event.model_dump_json() for event in result.trace)
    assert secret not in trace and str(root) not in trace and "project.md" not in trace
    assert secret in result.model_dump_json()  # Report artifact, not a diagnostic log.
    assert caplog.text == capsys.readouterr().out == ""


@pytest.mark.parametrize("error", [RuntimeError("PRIVATE_API_EXCEPTION"), TimeoutError("PRIVATE_API_EXCEPTION")])
def test_failed_model_request_consumes_budget_without_leaking_exception(root, error):
    flow, mock = session([error])
    result = flow.run()
    assert result.status == "model_error" and result.llm_requests == 1
    assert "PRIVATE_API_EXCEPTION" not in result.model_dump_json()


def test_budget_client_blocks_calls_and_counts_failed_attempts():
    mock = MockLLMClient([RuntimeError("failure"), finish()])
    client = BudgetedLLMClient(mock, max_requests=1)
    with pytest.raises(RuntimeError):
        client.complete([], [])
    with pytest.raises(LLMBudgetExceeded):
        client.complete([], [])
    assert client.request_count == len(mock.requests) == 1


def test_no_resume_on_finished_session(root):
    flow, _ = session([finish()])
    flow.run()
    with pytest.raises(ValueError):
        flow.resume("not a pending reply")


def test_factory_reuses_day4_agent_and_one_budget_for_all_stages(root):
    path = root / "resume.md"
    path.write_text(RESUME, encoding="utf-8")
    mock = MockLLMClient([
        LLMResponse(tool_calls=[ToolCall(id="initial", name="match_resume_to_job", arguments={})]),
        response({"title": "Intern", "required_skills": ["SQL"], "preferred_skills": []}),
        response({"assessments": [{"skill": "SQL", "status": "not_found", "quotes": [], "reasoning": "No evidence"}]}),
        LLMResponse(final_answer="Initial matching done."), search(), assessment(), finish(),
    ])
    flow = start_cost_aware_matching(mock, str(path), "SQL required", ["project.md"], max_llm_requests=7)
    result = flow.run()
    assert result.status == "finished"
    assert result.initial_report.score.score == 0 and result.report.score.score == 100
    assert result.llm_requests == len(mock.requests) == 7
    assert mock.requests[3].messages[-1].tool_call_id == "initial"


def test_offline_demo_is_network_free_and_shows_three_scenarios(capsys):
    from examples.demo_autonomous_evidence import main
    assert main([]) == 0
    output = capsys.readouterr().out
    assert "A：SEARCH → FINISH" in output and "0 → 100" in output
    assert "B：ASK_USER" in output and "waiting_for_user" in output
    assert "B 收到回复后：ASK_USER → FINISH" in output and "C：FINISH" in output


def test_paid_demo_cannot_start_without_opt_in():
    from examples.demo_autonomous_evidence import main
    with pytest.raises(SystemExit) as caught:
        main(["--deepseek"])
    assert caught.value.code == 2


def test_initial_matching_failure_does_not_start_autonomous_phase(root):
    path = root / "resume.md"
    path.write_text(RESUME, encoding="utf-8")
    mock = MockLLMClient([LLMResponse(final_answer="No initial tool report")])
    with pytest.raises(RuntimeError, match="Initial matching"):
        start_cost_aware_matching(mock, str(path), "SQL required", [])
    assert len(mock.requests) == 1


@pytest.mark.parametrize("limit", [0, -1, True, "2"])
def test_invalid_model_budget_limit(limit):
    with pytest.raises(ValueError):
        BudgetedLLMClient(MockLLMClient([]), max_requests=limit)


def test_wrong_resume_snapshot_cannot_be_used_for_supplemental_validation(root):
    with pytest.raises(ValueError, match="snapshot"):
        EvidenceGatheringSession(BudgetedLLMClient(MockLLMClient([])), initial(), "changed resume", ProjectEvidenceSearch([]))


def test_unknown_target_does_not_copy_untrusted_text_into_trace(root):
    secret = "PRIVATE_TEXT_AS_SKILL"
    flow, _ = session([search(skill=secret)], ["project.md"])
    result = flow.run()
    assert result.status == "model_error"
    assert secret not in "\n".join(event.model_dump_json() for event in result.trace)


def test_user_cannot_cite_an_answer_as_a_project_file(root):
    flow, _ = session([ask(), search(), assessment("User claims SQL skill", "user_reply"), finish()])
    flow.run()
    result = flow.resume("User claims SQL skill", additional_sources=["project.md"])
    assert result.status == "finished" and result.report.score.score == 0
    assert result.report.skills[0].evidence == []


def test_paid_demo_interactive_resume_uses_only_injected_mock(root, monkeypatch, capsys):
    from examples import demo_autonomous_evidence as demo
    from src import deepseek

    (root / "matching_resume.md").write_text(RESUME, encoding="utf-8")
    (root / "matching_job.md").write_text("SQL required", encoding="utf-8")
    monkeypatch.setattr(demo, "EXAMPLES_DIRECTORY", root)
    scripted = MockLLMClient([
        LLMResponse(tool_calls=[ToolCall(id="initial", name="match_resume_to_job", arguments={})]),
        response({"title": "Intern", "required_skills": ["SQL"], "preferred_skills": []}),
        response({"assessments": [{"skill": "SQL", "status": "not_found", "quotes": [], "reasoning": "No evidence"}]}),
        LLMResponse(final_answer="Initial matching done."), ask(), finish(),
    ])
    scripted.close = Mock()
    monkeypatch.setattr(deepseek, "DeepSeekLLMClient", lambda **kwargs: scripted)
    monkeypatch.setattr("builtins.input", lambda prompt: "我做过 SQL 项目，但没有文件。")
    assert demo.main(["--deepseek", "--run", "--interactive"]) == 0
    output = capsys.readouterr().out
    assert "waiting_for_user" in output and "收到用户回复后" in output
    assert "分数：0 → 0" in output
    assert len(scripted.requests) == 6
    scripted.close.assert_called_once()


def test_missing_material_metadata_is_tool_error_not_a_model_exception(root):
    flow, mock = session([finish()], ["project.md"])
    (root / "project.md").unlink()
    result = flow.run()
    assert result.status == "tool_error"
    assert not mock.requests


def test_factory_rejects_invalid_rounds_before_initial_model_calls(root):
    mock = MockLLMClient([])
    with pytest.raises(ValueError):
        start_cost_aware_matching(mock, "unused.md", "JD", [], max_rounds=0)
    assert not mock.requests


def test_sql_phrase_recall_runs_reevaluation_without_renaming_requirement(root):
    report = initial(required=["SQL查询"])
    flow, mock = session([search(skill="SQL查询"), assessment(skill="SQL查询"), finish()],
                         ["project.md"], report=report)
    result = flow.run()
    assert result.status == "finished"
    assert result.report.job.required_skills == ["SQL查询"]
    assert result.report.skills[0].skill == "SQL查询"
    assert result.report.skills[0].status == "supported"
    assert result.report.score.score == 100
    assert len(mock.requests) == 3


@pytest.mark.parametrize("skill", ["SQL查询", "SQL queries"])
def test_phrase_recall_checks_other_negative_mentions_before_granting_credit(root, skill):
    resume = "I have never used SQL."
    flow, _ = session([search(skill=skill), assessment(skill=skill), finish()], ["project.md"],
                      report=initial(required=[skill], resume=resume), resume=resume)
    result = flow.run()
    assert result.report.skills[0].status == "uncertain"
    assert result.report.score.score == 0
