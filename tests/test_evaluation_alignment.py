import copy
import hashlib
import json
from pathlib import Path

import pytest

from evaluation.alignment import (
    RULES_VERSION, combined_status, evaluate_aligned, jd_bindings,
    map_prediction, skill_key,
)
from evaluation.dataset import load_dataset, verify_gold_freeze
from evaluation.methods import Prediction
from evaluation.metrics import evaluate
from evaluation.rescore import rescore_report, write_rescore
from test_evaluation_metrics import make_run


ROOT = Path(__file__).resolve().parent.parent


@pytest.mark.parametrize("name", ["SQL", "SQL querying", " SQL Queries ", "SQL查询", "sql 查询"])
def test_explicit_complete_aliases(name):
    assert skill_key(name) == "sql"


@pytest.mark.parametrize("left,right", [
    ("SQL", "NoSQL"), ("SQL", "MySQL"),
    ("SQL querying", "SQL production experience"),
    ("RAG", "retrieval-only"), ("RAG", "retrieval"),
    ("Docker", "documentation"), ("Docker", "Docker documentation"),
    ("SQL", "SQLAlchemy"), ("SQL", "SQL querying performance optimization"),
])
def test_skill_boundaries_are_not_substring_matches(left, right):
    assert skill_key(left) != skill_key(right)


def test_rag_complete_alias_does_not_grant_retrieval_full_rag_credit():
    assert skill_key("retrieval augmented generation") == skill_key("RAG")
    case = load_dataset().cases[1]
    metrics = evaluate_aligned(case, make_run(case, [Prediction(skill="retrieval-only", status="supported")]))
    assert metrics["skill_correct"] == 0 and metrics["skill_total"] == 2


@pytest.mark.parametrize("condition", ["Experience with real business data in production",
    "SQL querying on real business data in production", "SQL production experience"])
def test_conditions_retain_separate_slots_and_require_jd_binding(condition):
    case = load_dataset().cases[4]
    binding = jd_bindings(case)
    mapped = map_prediction(condition, {"sql": "SQL"}, binding)
    assert mapped["kind"] == "condition" and mapped["conditions"]
    assert mapped["reason"] == "declared_condition_and_explicit_JD_binding"
    assert map_prediction(condition, {"sql": "SQL"}, {})["kind"] == "unexpected"


def test_ambiguous_unqualified_condition_is_not_attached():
    mapped = map_prediction("production experience", {"sql": "SQL", "python": "Python"},
                            {"sql": {"production"}, "python": {"production"}})
    assert mapped["kind"] == "unexpected"
    assert map_prediction("SQL production experience", {"sql": "SQL"},
                          {"sql": {"production"}})["kind"] == "condition"


def test_condition_binding_is_not_inferred_from_keywords(monkeypatch):
    case = load_dataset().cases[4]
    monkeypatch.setattr("evaluation.alignment.read_source", lambda _: "Required: SQL. Docker production experience.")
    assert jd_bindings(case) == {}
    monkeypatch.setattr("evaluation.alignment.read_source", lambda _: "SQL querying must include experience with production experience.")
    assert jd_bindings(case) == {"sql": {"production"}}


@pytest.mark.parametrize("base,conditions,expected", [
    ("partial", [("production", "not_found")], "partial"),
    ("supported", [("production", "not_found")], "partial"),
    ("supported", [("production", "partial")], "partial"),
    ("supported", [("production", "uncertain")], "uncertain"),
    ("partial", [("production", "supported")], "partial"),
    ("supported", [("production", "supported")], "uncertain"),
    ("supported", [("production", "supported"), ("real_business_data", "supported")], "supported"),
    ("supported", [("production", "supported"), ("production", "not_found")], "uncertain"),
    ("not_found", [("production", "supported")], "not_found"),
    ("uncertain", [("production", "supported")], "uncertain"),
])
def test_conservative_condition_composition(base, conditions, expected):
    mappings = [{"conditions": [slot], "status": status} for slot, status in conditions]
    assert combined_status(base, mappings, {"production", "real_business_data"}) == expected


def test_condition_cannot_replace_missing_skill_or_remove_unknown_penalty():
    case = load_dataset().cases[4]
    run = make_run(case, [Prediction(skill="production experience", status="supported"),
                          Prediction(skill="NoSQL", status="supported")])
    metrics = evaluate_aligned(case, run)
    assert metrics["skill_correct"] == 0 and metrics["skill_total"] == 2
    assert metrics["alignment"]["judgments"][0]["reason"] == "missing_primary"


@pytest.mark.parametrize("second_status", ["partial", "not_found"])
def test_duplicate_primary_alias_claims_are_not_silently_merged(second_status):
    case = load_dataset().cases[4]
    metrics = evaluate_aligned(case, make_run(case, [Prediction(skill="SQL", status="partial"),
        Prediction(skill="SQL querying", status=second_status)]))
    assert metrics["skill_correct"] == 0 and metrics["duplicate_skill_predictions"] == 1
    assert metrics["alignment"]["judgments"][0]["reason"] == "duplicate_primary"


def test_unknown_production_phrase_is_still_penalized():
    case = load_dataset().cases[4]
    metrics = evaluate_aligned(case, make_run(case, [Prediction(skill="SQL", status="partial"),
        Prediction(skill="production leadership experience", status="not_found")]))
    assert (metrics["skill_correct"], metrics["skill_total"]) == (1, 2)


@pytest.mark.parametrize("case_id,expected_old,expected_new", [
    ("02", [0, 1, 1], [0, 1, 1]), ("05", [.5, .5, 0], [1, 1, 1]),
])
def test_saved_live_predictions_unchanged_and_same_rules_for_all_methods(case_id, expected_old, expected_new):
    source = json.loads((ROOT / f"evaluation/reports/deepseek-case{case_id}-run01/real.json").read_text())
    before = copy.deepcopy(source)
    result = rescore_report(source, load_dataset())
    assert source == before
    assert [row["original_metrics"]["skill_status_accuracy"] for row in result["runs"]] == expected_old
    assert [row["metrics"]["skill_status_accuracy"] for row in result["runs"]] == expected_new
    for old, new in zip(source["runs"], result["runs"], strict=True):
        assert new["run"] == old["run"]
        assert new["metrics"]["evidence_validity"] == old["metrics"]["evidence_validity"]
        assert new["metrics"]["useful_retrieval_rate"] == old["metrics"]["useful_retrieval_rate"]
        assert len(new["metrics"]["alignment"]["mappings"]) == len(old["run"]["predictions"])
    assert result["rules_version"] == RULES_VERSION
    assert result == rescore_report(source, load_dataset())


def test_legacy_evaluator_remains_reproducible():
    case = load_dataset().cases[4]
    run = make_run(case, [Prediction(skill="SQL querying", status="partial")])
    assert evaluate(case, run)["skill_status_accuracy"] == 0
    assert evaluate_aligned(case, run)["skill_status_accuracy"] == 1


def test_rescore_uses_no_gold_status_to_choose_mappings():
    case = load_dataset().cases[4]
    run = make_run(case, [Prediction(skill="SQL querying", status="partial"),
                          Prediction(skill="production experience", status="not_found")])
    first = evaluate_aligned(case, run)
    changed = case.model_copy(deep=True)
    changed.gold[0].status = "supported"
    second = evaluate_aligned(changed, run)
    assert first["alignment"] == second["alignment"]
    assert first["skill_correct"] == 1 and second["skill_correct"] == 0


def test_rescore_writes_fresh_versioned_artifacts_and_preserves_source(tmp_path):
    source = ROOT / "evaluation/reports/deepseek-case05-run01/real.json"
    before = source.read_bytes()
    report = write_rescore(source, tmp_path / "new")
    assert report["source_sha256"] == hashlib.sha256(before).hexdigest()
    assert source.read_bytes() == before
    assert (tmp_path / "new/re-scored.md").is_file()
    assert json.loads((tmp_path / "new/re-scored.json").read_text()) == report
    with pytest.raises(ValueError, match="fresh"):
        write_rescore(source, tmp_path / "new")
    verify_gold_freeze(load_dataset())


def test_source_dataset_drift_and_mixed_modes_rejected():
    source = json.loads((ROOT / "evaluation/reports/deepseek-case05-run01/real.json").read_text())
    source["dataset_fingerprint"] = "different"
    with pytest.raises(ValueError, match="dataset"):
        rescore_report(source, load_dataset())
    source["dataset_fingerprint"] = verify_gold_freeze(load_dataset())["dataset_fingerprint"]
    source["runs"][0]["run"]["mode"] = "mock"
    with pytest.raises(ValueError, match="Mixed"):
        rescore_report(source, load_dataset())
