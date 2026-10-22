"""User-reviewed labels, integrity seal, evidence polarity and paired controls."""

import hashlib
import json
import shutil
from pathlib import Path

import pytest
from pydantic import ValidationError

from evaluation.clients import ScriptedLLM
from evaluation.dataset import Case, GoldEvidence, load_dataset, verify_gold_freeze
from evaluation.methods import Prediction
from evaluation.metrics import evaluate
from evaluation.report import build_report, markdown
from evaluation.run import run_suite
from test_evaluation_metrics import make_run, ref


ROOT = Path(__file__).resolve().parent.parent
ARCHIVE = ROOT / "evaluation/versions/day6-v1-draft"


def test_reviewed_distribution_and_retained_gold():
    from collections import Counter
    dataset = load_dataset()
    assert dataset.version == "gold-v1"
    assert Counter(skill.status for case in dataset.cases for skill in case.gold) == {
        "supported": 6, "partial": 1, "not_found": 6}
    old = json.loads((ARCHIVE / "evaluation/cases.json").read_text())
    for index in [0, 2, 5, 6, 7, 8, 10, 11]:
        assert dataset.cases[index].model_dump() == Case.model_validate(old["cases"][index]).model_dump()
    gold = dataset.cases[3].gold[0]
    assert gold.status == "not_found" and gold.evidence[1].relation == "negates"
    assert dataset.cases[4].gold[0].evidence[2].relation == "limits"


@pytest.mark.parametrize("index", [1, 9])
def test_rag_revisions_have_all_three_stages_and_unchanged_jd(index):
    case = load_dataset().cases[index]
    evidence = case.gold[0].evidence[0]
    material = (ROOT / "examples" / evidence.source).read_text()
    assert case.gold[0].status == "supported" and evidence.quote == material.strip()
    assert evidence.start_line == 1 and evidence.end_line == 3
    assert all(stage in material for stage in ["Retrieval:", "Augmentation:", "Generation:"])
    assert "LLM prompt as context" in material and "produce answers" in material
    assert (ROOT / "examples" / case.jd).read_bytes() == (ARCHIVE / "examples" / case.jd).read_bytes()


def test_archive_is_byte_preserved_and_only_two_source_files_changed():
    archive = json.loads((ARCHIVE / "ARCHIVE.json").read_text())
    changed_inputs = []
    for name, digest in archive["sha256"].items():
        assert hashlib.sha256((ARCHIVE / name).read_bytes()).hexdigest() == digest
        if name.startswith("examples/") and hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != digest:
            changed_inputs.append(name)
    assert sorted(changed_inputs) == ["examples/evaluation/02/b_rag.md", "examples/evaluation/10/rag.md"]


def test_mock_original_actions_states_scores_and_reasons_are_not_fitted_to_gold():
    old = json.loads((ARCHIVE / "evaluation/mock_scripts.json").read_text())
    current = json.loads((ROOT / "evaluation/mock_scripts.json").read_text())
    for case_id in ["02", "10"]:
        current[case_id]["supplemental"]["RAG"]["citations"] = old[case_id]["supplemental"]["RAG"]["citations"]
    assert current == old
    assert ScriptedLLM("04").script["supplemental"]["SQL"]["status"] == "uncertain"


@pytest.mark.parametrize("relation", ["supports", "partial", "contradicts", "irrelevant", "limits", "negates"])
def test_evidence_relation_vocabulary_remains_backward_compatible(relation):
    assert GoldEvidence(source="project.md", quote="example", start_line=1, end_line=1, relation=relation).relation == relation


@pytest.mark.parametrize("status", ["supported", "partial"])
def test_limit_only_is_verbatim_but_never_positive_skill_support(status):
    case = load_dataset().cases[4]
    run = make_run(case, [Prediction(skill="SQL", status=status, citations=[ref(case.gold[0].evidence[2])])])
    stats = evaluate(case, run)
    assert stats["evidence_validity"] == 1 and stats["semantic_positive_support"] == 0
    assert stats["positive_citations_reviewed"] == 1
    assert stats["evidence_audit"][0]["semantic_relations"] == ["limits"]


def test_positive_practice_and_limit_can_jointly_support_partial():
    case = load_dataset().cases[4]
    source = case.authorized_sources[0]
    quote = (ROOT / "examples" / source).read_text().strip()
    citation = ref(case.gold[0].evidence[1], quote=quote, end_line=3)
    stats = evaluate(case, make_run(case, [Prediction(skill="SQL", status="partial", citations=[citation])]))
    assert stats["evidence_validity"] == stats["semantic_positive_support"] == 1
    assert stats["evidence_audit"][0]["semantic_relations"] == ["limits", "partial"]


@pytest.mark.parametrize("relation", ["negates", "contradicts"])
def test_denial_and_legacy_conflict_do_not_count_as_positive_support(relation):
    case = load_dataset().cases[3].model_copy(deep=True)
    case.gold[0].evidence[1].relation = relation
    stats = evaluate(case, make_run(case, [Prediction(skill="SQL", status="supported", citations=[ref(case.gold[0].evidence[1])])]))
    assert stats["evidence_validity"] == 1 and stats["semantic_positive_support"] == 0


@pytest.mark.parametrize("relation", ["limits", "negates"])
def test_positive_gold_cannot_be_justified_only_by_nonpositive_relation(relation):
    payload = load_dataset().cases[4].model_dump()
    payload["gold"][0]["evidence"] = [payload["gold"][0]["evidence"][2]]
    payload["gold"][0]["evidence"][0]["relation"] = relation
    with pytest.raises(ValidationError):
        Case.model_validate(payload)


def test_freeze_matches_final_37_files_and_default_loader_verifies_it(monkeypatch):
    import evaluation.dataset as module
    dataset = load_dataset()
    seal = verify_gold_freeze(dataset)
    assert len(seal["sha256"]) == 37 and seal["dataset_version"] == "gold-v1"
    def reject(_):
        raise ValueError("seal sentinel")
    monkeypatch.setattr(module, "verify_gold_freeze", reject)
    with pytest.raises(ValueError, match="seal sentinel"):
        load_dataset()


@pytest.mark.parametrize("name", ["evaluation/cases.json", "evaluation/GOLD_NOTES.md", "examples/evaluation/02/b_rag.md"])
def test_frozen_content_drift_fails_without_resealing(tmp_path, name):
    dataset = load_dataset()
    seal = verify_gold_freeze(dataset)
    for file in [*seal["sha256"], "evaluation/GOLD_V1_FREEZE.json"]:
        target = tmp_path / file
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(ROOT / file, target)
    with (tmp_path / name).open("a") as handle:
        handle.write("changed")
    before = (tmp_path / "evaluation/GOLD_V1_FREEZE.json").read_bytes()
    with pytest.raises(ValueError, match="content changed"):
        verify_gold_freeze(dataset, root=tmp_path)
    assert (tmp_path / "evaluation/GOLD_V1_FREEZE.json").read_bytes() == before


def test_freeze_rejects_extra_paths_before_reading_them(tmp_path):
    dataset = load_dataset()
    seal = verify_gold_freeze(dataset)
    seal["sha256"]["../not-authorized.txt"] = "irrelevant"
    (tmp_path / "evaluation").mkdir()
    (tmp_path / "evaluation/GOLD_V1_FREEZE.json").write_text(json.dumps(seal))
    with pytest.raises(ValueError, match="file set/version mismatch"):
        verify_gold_freeze(dataset, root=tmp_path)


def test_fault_controls_are_actual_same_input_runs_and_not_subsets():
    dataset = load_dataset()
    report = run_suite(dataset)
    normal = report["normal_access"]
    assert normal["fault_case_ids"] == ["10", "11"] and normal["controls_complete"]
    assert len(report["runs"]) == 36 and len(normal["controls"]) == 6
    for method in ["single", "fixed", "agent"]:
        assert normal["non_fault_subset"][method]["runs"] == 10
        assert normal["control_summary"][method]["runs"] == 2
        assert normal["all_cases_with_controls"][method]["runs"] == 12
        assert normal["all_cases_with_controls"][method]["error_rate"] == 0
        assert report["execution_cost"][method]["llm_requests"] == (
            report["summary"][method]["llm_requests"] + normal["control_summary"][method]["llm_requests"])
    for row in normal["controls"]:
        control = row["run"]
        original = next(item["run"] for item in report["runs"] if
                        (item["run"]["case_id"], item["run"]["method"]) == (control["case_id"], control["method"]))
        assert control["condition"] == "normal_access_control" and control["injected_fault"] is None
        for field in ["input_fingerprint", "authorized_sources", "budgets", "initial_checkpoint_fingerprint"]:
            assert original[field] == control[field]
    assert report["summary"]["agent"]["skill_correct"] == report["summary"]["fixed"]["skill_correct"] == 8
    assert report["summary"]["single"]["skill_correct"] == 6
    assert report["normal_access"]["all_cases_with_controls"]["agent"]["skill_correct"] == 10
    assert "fault-disabled controls" in markdown(report)


def test_report_without_controls_never_claims_all_case_normal_access():
    from evaluation.clients import ObservedLLM
    from evaluation.methods import run_method
    dataset = load_dataset()
    case = dataset.cases[9]
    run = run_method(case, "agent", ObservedLLM(ScriptedLLM(case.id)))
    report = build_report(dataset, [run])
    assert not report["normal_access"]["controls_complete"]
    assert report["normal_access"]["all_cases_with_controls"] == {}
    assert "no all-cases normal-access result is claimed" in markdown(report)


def test_live_control_budget_must_include_both_conditions_before_client_creation():
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("Paid client must not be created")
    with pytest.raises(ValueError, match="Total request cap"):
        run_suite(load_dataset(), mode="real", allow_paid=True, case_ids=["10"], normal_access_control=True,
                  max_total_requests=25, client_factory=forbidden)
    assert calls == []


def test_in_memory_gold_edit_cannot_be_run_under_frozen_version():
    dataset = load_dataset().model_copy(deep=True)
    dataset.cases[3].gold[0].status = "uncertain"
    calls = []
    def forbidden(*args):
        calls.append(args)
        raise AssertionError("No model call on modified Gold")
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        run_suite(dataset, client_factory=forbidden)
    assert calls == []


def test_controls_reject_changed_budgets_and_duplicate_pairs():
    from evaluation.clients import ObservedLLM
    from evaluation.methods import run_method
    dataset = load_dataset()
    case = dataset.cases[9]
    configured = run_method(case, "agent", ObservedLLM(ScriptedLLM(case.id)))
    control = run_method(case.model_copy(update={"fault": None}), "agent",
                         ObservedLLM(ScriptedLLM(case.id, normal_access_control=True)))
    control.condition = "normal_access_control"
    with pytest.raises(ValueError, match="Duplicate normal-access"):
        build_report(dataset, [configured], normal_access_runs=[control, control])
    control.budgets["max_requests"] = 13
    with pytest.raises(ValueError, match="paired rerun"):
        build_report(dataset, [configured], normal_access_runs=[control])
