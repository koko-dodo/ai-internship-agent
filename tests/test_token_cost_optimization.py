import json

import pytest

from evaluation.dataset import load_dataset, verify_gold_freeze
from evaluation.report import dumps
from evaluation.token_cost_ab import OriginalFormattingSession, build_ab
from src.autonomy import EvidenceGatheringSession
from src.schemas import GatheringDecision, SupplementalAssessment


@pytest.mark.parametrize("model", [GatheringDecision, SupplementalAssessment])
def test_json_formatting_preserves_all_fields_and_string_contents(model):
    schema = model.model_json_schema()
    data = {"user_statements_unverified": [{"answer": '  SQL 查询 : 中文, "quotes"\nline  two  ', "verified": False}],
            "allowed_actions": ["SEARCH", "ASK_USER", "FINISH"],
            "authorized_materials": [{"source": "project.md", "estimated_read_units": 1}],
            "search_history": [{"error_code": "duplicate_search", "success": False}],
            "budgets": {"remaining": 2}, "empty": None}
    before = OriginalFormattingSession._encode_request(schema, data, model)
    after = EvidenceGatheringSession._encode_request(schema, data, model)
    assert json.loads(before) == json.loads(after) == {"schema": schema, "data": data}
    if model is GatheringDecision:
        assert len(after) < len(before)
    else:
        assert before == after  # Evidence assessment prompts are byte identical.


@pytest.fixture(scope="module")
def ab():
    return build_ab()


def test_all_scripted_and_recorded_response_replays_preserve_behavior(ab):
    assert len(ab["rows"]) == 14
    for row in ab["rows"]:
        assert all(row["checks"].values()), row
        old, new = row["before"], row["after"]
        assert new["decision_context_characters"] < old["decision_context_characters"]
        assert new["decision_calls"] == old["decision_calls"]
        assert new["llm_requests"] == old["llm_requests"]
        assert new["retrieval_attempts"] == old["retrieval_attempts"]
        assert new["waiting_events"] == old["waiting_events"]
        assert new["error_codes"] == old["error_codes"]
        assert new["token_usage"] == old["token_usage"] == "unavailable"


@pytest.mark.parametrize("case_id,decisions,requests,retrievals", [("02", 2, 5, 1), ("05", 4, 7, 2)])
def test_saved_response_replay_counts_are_not_claimed_as_new_live_usage(ab, case_id, decisions, requests, retrievals):
    row = next(row for row in ab["rows"] if row["fixture"] == "saved_response_replay" and row["case_id"] == case_id)
    assert row["after"]["decision_calls"] == decisions
    assert row["after"]["llm_requests"] == requests
    assert row["after"]["retrieval_attempts"] == retrievals
    assert row["after"]["status"] == "finished"
    assert ab["token_usage"] == "unavailable"


def test_waiting_resume_permissions_io_and_invalid_action_recovery_preserved(ab):
    rows = {row["case_id"]: row for row in ab["rows"] if row["fixture"] == "scripted_mock"}
    assert rows["07"]["after"]["status"] == "waiting_for_user"
    assert rows["08"]["after"]["waiting_events"] == 1
    assert rows["08"]["after"]["status"] == "finished"
    assert rows["10"]["after"]["status"] == "permission_denied"
    assert rows["11"]["after"]["status"] == "tool_error"
    assert "invalid_target" in rows["12"]["after"]["error_codes"]
    assert rows["12"]["after"]["status"] == "finished"


def test_ab_is_reproducible_with_frozen_gold_and_without_serializing_prompts(ab):
    assert dumps(build_ab()) == dumps(ab)
    verify_gold_freeze(load_dataset())
    assert "原文" not in dumps(ab)
    assert "model_outputs" not in dumps(ab)
    assert "user_statements_unverified" not in dumps(ab)
