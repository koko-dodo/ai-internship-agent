"""Offline regressions for the real Day 5 log; no vendor API requests."""

import json

import pytest

from src import evidence_search
from src.autonomy import BudgetedLLMClient, EvidenceGatheringSession
from src.evidence_search import ProjectEvidenceSearch
from src.llm import LLMResponse, MockLLMClient
from src.matching import build_match_report
from src.schemas import JobPosting, SemanticEvidenceEvaluation


PRACTICE = "本人负责 SQL 查询模块，使用 JOIN 和 GROUP BY 汇总借阅记录。"
LIMIT = "项目使用虚构数据，没有部署到真实业务环境。"
RESUME = "使用 Python、Pandas 和 Git 完成项目。\n\n完成 SQL 基础课程，尚无实际业务项目经验。"


def response(payload):
    return LLMResponse(final_answer=json.dumps(payload, ensure_ascii=False))


def search(source="project.md"):
    return response({"action": "SEARCH", "skill": "SQL查询", "source": source, "reason": "补充关键技能文件证据。"})


def ask():
    return response({"action": "ASK_USER", "skill": "SQL查询", "reason": "没有可继续检索的新来源。",
                     "question": "请提供 SQL 查询用于真实业务数据的项目原文，可以吗？"})


def finish():
    return response({"action": "FINISH", "reason": "保留已验证的部分匹配，未证实业务经验。"})


def assessment(status="partial", quotes=None):
    return response({"skill": "SQL查询", "status": status, "reasoning": "有 SQL 实践，真实业务子要求仍缺证。",
                     "citations": [{"source": "project.md", "quote": text} for text in (quotes if quotes is not None else [PRACTICE, LIMIT])]})


def baseline(*, business=True, resume=RESUME, sql_skill="SQL查询"):
    job = JobPosting(title="Intern", required_skills=["Python", "Pandas", sql_skill, "Git"],
                     preferred_skills=["Docker", "PyTorch"],
                     description="具备 SQL 查询经验，能够结合真实业务数据进行分析。" if business else "具备 SQL 查询实践。")
    return build_match_report(job, SemanticEvidenceEvaluation.model_validate({"assessments": [
        {"skill": skill, "status": "supported", "quotes": [resume.split("\n")[0]], "reasoning": "原文项目证据"}
        for skill in ["Python", "Pandas", "Git"]
    ] + [{"skill": sql_skill, "status": "partial", "quotes": [resume.split("\n")[-1]], "reasoning": "只有部分证据"}]
      + [{"skill": skill, "status": "not_found", "quotes": [], "reasoning": "简历证据不足"} for skill in ["Docker", "PyTorch"]]}),
      resume, "resume.md")


@pytest.fixture
def root(tmp_path, monkeypatch):
    path = tmp_path / "examples"
    path.mkdir()
    (path / "project.md").write_text(PRACTICE + "\n\n" + LIMIT, encoding="utf-8")
    for name in ["empty1.md", "empty2.md", "empty3.md"]:
        (path / name).write_text("Team meeting notes.", encoding="utf-8")
    monkeypatch.setattr(evidence_search, "EXAMPLES_DIRECTORY", path)
    return path


def flow(responses, *, materials=("project.md",), rounds=5, calls=12, searches=3,
         resume_rounds=2, business=True, resume=RESUME):
    mock = MockLLMClient(responses)
    session = EvidenceGatheringSession(BudgetedLLMClient(mock, calls), baseline(business=business, resume=resume),
                                       resume, ProjectEvidenceSearch(materials, searches),
                                       max_rounds=rounds, resume_rounds=resume_rounds)
    return session, mock


@pytest.mark.parametrize("status", ["supported", "partial"])
@pytest.mark.parametrize("limitation", [LIMIT, "使用模拟数据，尚无实际业务项目经验。", "Used synthetic data; not deployed to production."])
def test_sql_practice_and_business_limit_is_partial_not_global_denial(root, status, limitation):
    (root / "project.md").write_text(PRACTICE + "\n\n" + limitation, encoding="utf-8")
    session, _ = flow([search(), assessment(status, [PRACTICE, limitation]), finish()])
    result = session.run()
    sql = next(item for item in result.report.skills if item.skill == "SQL查询")
    assert sql.status == "partial"
    assert result.initial_report.score.score == result.report.score.score == 70
    assert any("子要求" in note for note in sql.validation_notes)
    assert {PRACTICE, limitation}.issubset({item.quote for item in sql.evidence})


def test_production_limit_does_not_reduce_a_practice_only_requirement(root):
    session, _ = flow([search(), assessment("supported"), finish()], business=False)
    result = session.run()
    assert result.report.skills[2].status == "supported"
    assert result.report.score.score == 80


@pytest.mark.parametrize("denial", [
    "本人没有使用 SQL 做过查询项目。",
    "I have never used SQL.",
    "我没有使用 SQL，也没有部署到生产环境。",
    "No experience:\nSQL",
])
def test_real_skill_denial_can_lower_score_with_locatable_basis(root, denial):
    (root / "project.md").write_text(PRACTICE + "\n\n" + denial, encoding="utf-8")
    session, _ = flow([search(), assessment("partial", [PRACTICE]), finish()])
    result = session.run()
    sql = result.report.skills[2]
    assert sql.status == "uncertain"
    assert result.initial_report.score.score == 70 and result.report.score.score == 60
    assert any("技能否定依据 project.md:" in note for note in sql.validation_notes)
    assert any(denial in item.context for item in sql.evidence)


def test_unrelated_skill_denial_in_same_paragraph_does_not_negate_sql(root):
    text = PRACTICE + "\n没有使用 Docker。"
    (root / "project.md").write_text(text, encoding="utf-8")
    session, _ = flow([search(), assessment("supported", [text]), finish()], business=False)
    assert session.run().report.skills[2].status == "supported"


@pytest.mark.parametrize("status", ["not_found", "uncertain"])
def test_context_limit_alone_cannot_erase_previously_verified_partial_practice(root, status):
    session, _ = flow([search(), assessment(status), finish()])
    result = session.run()
    assert result.report.skills[2].status == "partial" and result.report.score.score == 70


@pytest.mark.parametrize("next_action", [ask(), finish()])
def test_duplicate_feedback_identifies_pair_and_filters_search_schema(root, next_action):
    session, mock = flow([search(), assessment(), search(), next_action], searches=1)
    result = session.run()
    assert result.status in {"waiting_for_user", "finished"}
    request = json.loads(mock.requests[-1].messages[0].content.split("\n")[-1])
    data = request["data"]
    assert data["available_searches"] == []
    assert "SEARCH" not in data["allowed_actions"]
    assert "SEARCH" not in request["schema"]["properties"]["action"]["enum"]
    assert data["last_tool_result"]["source"] == "project.md"
    assert data["last_tool_result"]["skill"] == "SQL查询"
    assert data["last_tool_result"]["error_code"] == "duplicate_search"
    assert data["last_tool_result"]["reason"]
    assert data["search_history"][0]["success"] is True
    assert data["search_history"][1]["error_code"] == "duplicate_search"
    assert result.searches == 1


def test_exhausted_source_not_offered_for_same_target_even_with_other_skill_gaps(root):
    session, mock = flow([search(), assessment(), finish()])
    session.run()
    data = json.loads(mock.requests[-1].messages[0].content.split("\n")[-1])["data"]
    assert not any(pair["skill"] == "SQL查询" and pair["source"] == "project.md" for pair in data["available_searches"])


def test_stubborn_repeated_search_stops_after_explicit_feedback_without_more_reads(root, monkeypatch):
    original = evidence_search.read_resume
    reads = []
    def record(*args, **kwargs):
        reads.append(args)
        return original(*args, **kwargs)
    monkeypatch.setattr(evidence_search, "read_resume", record)
    session, mock = flow([search(), assessment(), search(), search(), ask()])
    result = session.run()
    assert result.status == "model_error" and "无进展" in result.reason
    assert result.trace[-1].error_code == "no_progress"
    assert result.searches == len(reads) == 1
    assert len(mock.requests) == 4


def test_ask_on_round_five_resumes_with_existing_request_budget(root):
    names = ["empty1.md", "empty2.md", "empty3.md"]
    session, mock = flow([*(search(name) for name in names), search(names[0]), ask(), finish()],
                         materials=names, rounds=5, calls=6)
    waiting = session.run()
    assert waiting.status == "waiting_for_user" and waiting.rounds == 5
    assert waiting.context["resume_rounds_available"] == 1
    result = session.resume("我做过课程 SQL 实践，但没有新的业务项目文件。")
    assert result.status == "finished" and result.rounds == 6
    assert result.llm_requests == len(mock.requests) == 6
    assert result.searches == 3 and result.report.score.score == 70


def test_recovery_window_is_granted_only_once(root):
    session, mock = flow([ask(), ask(), finish()])
    assert session.run().status == "waiting_for_user"
    result = session.resume("暂无可授权的新项目材料。")
    assert result.status == "step_limit" and "一次性" in result.reason
    assert result.question is None
    with pytest.raises(ValueError):
        session.resume("再次回答不能重置窗口。")
    assert len(mock.requests) == 2


def test_recovery_stops_after_two_decisions_even_when_api_budget_remains(root):
    session, mock = flow([ask(), search("empty1.md"), search("empty2.md"), finish()], materials=["empty1.md", "empty2.md"])
    session.run()
    result = session.resume("两份补充说明供核实。")
    assert result.status == "step_limit" and "恢复决策窗口" in result.reason
    assert result.rounds == len(mock.requests) == 3
    assert result.searches == 2 and session.client.remaining > 0


def test_recovery_request_budget_cannot_be_refilled(root):
    session, mock = flow([ask(), search(), assessment(), finish()], calls=2)
    session.run()
    result = session.resume("我声称有 SQL 经验。")
    assert result.status == "budget_exhausted" and result.searches == 0
    assert len(mock.requests) == 2


def test_shared_budget_spent_while_waiting_has_an_explicit_resume_failure(root):
    session, mock = flow([ask(), finish()], calls=2)
    session.run()
    session.client.complete([], [])
    result = session.resume("实际回复。")
    assert result.status == "budget_exhausted" and "恢复前" in result.reason
    assert result.question is None and result.context is None
    assert len(mock.requests) == 2


def test_disabled_recovery_never_creates_an_unresumable_wait(root):
    session, _ = flow([ask()], resume_rounds=0)
    result = session.run()
    assert result.status == "step_limit" and result.question is None
    assert "未启用" in result.reason


def test_reliability_demo_keeps_seventy_and_resumes_without_new_proof(capsys):
    from examples.demo_autonomous_evidence import reliability_demo
    reliability_demo()
    output = capsys.readouterr().out
    assert "D 可靠性复现：SEARCH → SEARCH → ASK_USER" in output
    assert "状态：waiting_for_user；分数：70 → 70；检索：1；LLM 请求：4" in output
    assert "状态：finished；分数：70 → 70；检索：1；LLM 请求：5" in output
    assert "保持 partial" in output


def latest_log_session(last_decisions, *, calls=12, rounds=5):
    """Exact latest action order; the real search tool runs against local files."""
    responses = [response({"action": "SEARCH", "skill": skill, "source": "project.md", "reason": "查询授权文件。"})
                 for skill in ["SQL", "Docker", "PyTorch"]]
    responses.insert(1, response({"skill": "SQL", "status": "partial", "reasoning": "实践存在，业务环境尚待核实。",
                                  "citations": [{"source": "project.md", "quote": text} for text in [PRACTICE, LIMIT]]}))
    mock = MockLLMClient(responses + last_decisions)
    session = EvidenceGatheringSession(BudgetedLLMClient(mock, calls), baseline(sql_skill="SQL"), RESUME,
                                       ProjectEvidenceSearch(["project.md"], 3), max_rounds=rounds)
    return session, mock


def sql_question(**overrides):
    return response({"action": "ASK_USER", "skill": "SQL", "reason": "仍需核实业务经验。",
                     "question": "请提供 SQL 查询用于真实业务数据的具体场景或项目原文。", **overrides})


def decision_request(mock):
    return json.loads(mock.requests[-1].messages[0].content.split("\n")[-1])


def test_latest_log_three_searches_then_ask_partial_sql(root):
    session, mock = latest_log_session([sql_question()])
    result = session.run()
    assert result.status == "waiting_for_user"
    assert result.rounds == 4 and result.llm_requests == 5 and result.searches == 3
    assert result.initial_report.score.score == result.report.score.score == 70
    assert result.context["skill"] == "SQL" and result.context["status"] == "partial"
    assert [(event.skill, event.candidate_count) for event in result.trace if event.event == "search"] == [
        ("SQL", 1), ("Docker", 0), ("PyTorch", 0)]
    request = decision_request(mock)
    assert request["data"]["available_searches"] == []
    assert request["data"]["allowed_actions"] == request["schema"]["properties"]["action"]["enum"] == ["ASK_USER", "FINISH"]
    assert {item["skill"] for item in request["data"]["ask_user_targets"]} == {"SQL", "Docker", "PyTorch"}


@pytest.mark.parametrize("bad_question,code", [
    ({"skill": None}, "invalid_action_arguments"),
    ({"skill": "到岗时间"}, "invalid_target"),
    ({"skill": "SQL查询"}, "invalid_target"),  # Must correct to the report's actual target.
    ({"skill": "Python"}, "invalid_target"),
    ({"question": "信息？"}, "invalid_action_arguments"),
    ({"source": "project.md"}, "invalid_action_arguments"),
])
def test_latest_log_invalid_ask_is_corrected_then_waits_and_resumes(root, bad_question, code):
    session, mock = latest_log_session([sql_question(**bad_question), sql_question(), finish()])
    waiting = session.run()
    assert waiting.status == "waiting_for_user" and waiting.rounds == 5
    assert waiting.searches == 3 and waiting.report.score.score == 70
    request = decision_request(mock)
    assert request["data"]["last_tool_result"]["error_code"] == code
    assert request["data"]["validation_corrections_remaining"] == 1
    assert any(event.error_code == code and event.success is False for event in waiting.trace)
    result = session.resume("我声称用过 SQL，但没有新的可授权项目文件。")
    assert result.status == "finished" and result.rounds == 6
    assert result.llm_requests == 7 and result.report.score.score == 70
    assert session._replies[-1]["verified"] is False


def test_missing_skill_is_structured_error_without_inference(root):
    missing = response({"action": "ASK_USER", "reason": "需补充信息。", "question": "请说明你的 SQL 项目经历。"})
    session, mock = flow([missing, finish()])
    assert session.run().status == "finished"
    assert decision_request(mock)["data"]["last_tool_result"]["error_code"] == "invalid_action_arguments"


@pytest.mark.parametrize("status", ["partial", "not_found", "uncertain"])
def test_ask_accepts_each_unresolved_status(root, status):
    session, _ = flow([ask()])
    session._report.skills[2].status = status
    result = session.run()
    assert result.status == "waiting_for_user" and result.context["status"] == status


def test_invalid_actions_have_only_two_corrections_no_budget_reset(root):
    invalid = response({"action": "ASK_USER", "skill": "PRIVATE-TARGET", "reason": "补充。", "question": "请补充更多相关的说明材料。"})
    session, mock = flow([invalid, invalid, invalid, finish()], rounds=10)
    result = session.run()
    assert result.status == "model_error" and result.trace[-1].error_code == "invalid_decision_limit"
    assert result.llm_requests == len(mock.requests) == result.rounds == 3
    assert result.searches == 0 and "PRIVATE-TARGET" not in result.model_dump_json()


def test_correction_allowance_is_shared_across_resume(root):
    invalid = response({"action": "ASK_USER", "reason": "缺字段。"})
    session, mock = flow([invalid, invalid, ask(), invalid, finish()], rounds=6)
    assert session.run().status == "waiting_for_user"
    result = session.resume("没有可以验证的新文件。")
    assert result.status == "model_error" and result.trace[-1].error_code == "invalid_decision_limit"
    assert len(mock.requests) == 4


@pytest.mark.parametrize("calls,rounds,status", [(1, 5, "budget_exhausted"), (12, 1, "step_limit")])
def test_corrections_cannot_extend_request_or_round_budget(root, calls, rounds, status):
    session, mock = flow([response({"action": "BAD"}), finish()], calls=calls, rounds=rounds)
    result = session.run()
    assert result.status == status and result.llm_requests == len(mock.requests) == 1


def test_correction_does_not_weaken_path_authorization(root):
    session, mock = flow([response({"action": "BAD"}), search("../private.md"), finish()])
    result = session.run()
    assert result.status == "permission_denied" and result.searches == 0
    assert len(mock.requests) == 2 and result.trace[-1].error_code == "access_denied"


def test_malformed_decision_json_is_recoverable_but_sdk_exception_is_terminal(root):
    session, mock = flow([LLMResponse(final_answer="{broken"), finish()])
    assert session.run().status == "finished" and len(mock.requests) == 2
    class BrokenClient:
        def complete(self, messages, tools):
            raise RuntimeError("SECRET-SDK-DETAILS")
    session.client = BudgetedLLMClient(BrokenClient())
    session._status = None
    result = session.run()
    assert result.status == "model_error" and result.trace[-1].error_code == "model_failure"
    assert session.client.request_count == 1 and "SECRET-SDK-DETAILS" not in result.model_dump_json()


def test_decision_schema_publishes_action_specific_arguments():
    from src.schemas import GatheringDecision
    from pydantic import ValidationError
    schema = GatheringDecision.model_json_schema()
    branches = {branch["properties"]["action"]["const"]: branch for branch in schema["oneOf"]}
    assert branches["SEARCH"]["required"] == ["skill", "source"]
    assert branches["ASK_USER"]["required"] == ["skill", "question"]
    assert branches["ASK_USER"]["properties"]["question"]["minLength"] == 8
    assert branches["ASK_USER"]["properties"]["source"] == {"type": "null"}
    assert branches["FINISH"]["properties"]["skill"] == {"type": "null"}
    assert GatheringDecision(action="FINISH", reason="无需继续。判定结束。 ").skill is None
    for payload in [{"action": "SEARCH", "skill": "SQL"}, {"action": "ASK_USER", "question": "请补充 SQL 项目材料。"},
                    {"action": "FINISH", "skill": "SQL"}]:
        with pytest.raises(ValidationError):
            GatheringDecision(reason="检查参数。", **payload)


def test_latest_log_demo_corrects_ask_then_waits_and_resumes(capsys):
    from examples.demo_autonomous_evidence import action_validation_demo
    action_validation_demo()
    output = capsys.readouterr().out
    assert "E 最新轨迹与参数纠正：SEARCH → SEARCH → SEARCH → ASK_USER → ASK_USER" in output
    assert "状态：waiting_for_user；分数：70 → 70；检索：3；LLM 请求：6" in output
    assert "SQL=1，Docker=0，PyTorch=0；参数反馈：invalid_target；SQL 状态：partial" in output
    assert "状态：finished；分数：70 → 70；检索：3；LLM 请求：7" in output
