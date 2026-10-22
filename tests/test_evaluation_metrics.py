import pytest

from evaluation.dataset import Citation, load_dataset
from evaluation.methods import Prediction, Run
from evaluation.metrics import aggregate, evaluate


def make_run(case, predictions, **overrides):
    return Run(case_id=case.id, scenario=case.scenario, method="agent", mode="mock", model="fixture",
               input_fingerprint="same", authorized_sources=case.authorized_sources, budgets={}, status="finished",
               predictions=predictions, cost={"llm_requests": 1, "api_requests": None,
               "token_usage": {"prompt_tokens": None, "completion_tokens": None, "total_tokens": None}}, **overrides)


def ref(evidence, **changes):
    return Citation(**{**evidence.model_dump(exclude={"relation"}), **changes})


def test_accuracy_counts_missing_unknown_duplicate_and_wrong_states():
    case = load_dataset().cases[0]
    correct = Prediction(skill="python", status="supported")
    run = make_run(case, [correct])
    assert evaluate(case, run)["skill_status_accuracy"] == .5
    run.predictions.append(Prediction(skill="InventedSkill", status="supported"))
    assert evaluate(case, run)["skill_status_accuracy"] == pytest.approx(1 / 3)
    run.predictions.append(Prediction(skill="Python", status="not_found"))
    metrics = evaluate(case, run)
    assert metrics["skill_status_accuracy"] == 0
    assert metrics["unexpected_skills"] == metrics["duplicate_skill_predictions"] == 1


@pytest.mark.parametrize("changes,valid", [({}, 1), ({"quote": "fabricated"}, 0),
    ({"quote": "  I implemented Python CSV validation with unit tests.  "}, 0), ({"quote": ""}, 0),
    ({"start_line": 100}, 0), ({"end_line": 100}, 0), ({"resume_sha256": "bad"}, 0),
    ({"source": "evaluation/02/b_rag.md"}, 0)])
def test_exact_evidence_location_and_hash_are_audited(changes, valid):
    case = load_dataset().cases[0]
    run = make_run(case, [Prediction(skill="Python", status="supported", citations=[ref(case.gold[0].evidence[0], **changes)])])
    metrics = evaluate(case, run)
    assert metrics["citation_valid"] == valid and metrics["citation_total"] == 1


def test_verbatim_docker_mention_is_not_semantic_support():
    case = load_dataset().cases[5]
    run = make_run(case, [Prediction(skill="Docker", status="supported", citations=[ref(case.gold[0].evidence[0])])])
    metrics = evaluate(case, run)
    assert metrics["evidence_validity"] == 1
    assert metrics["semantic_positive_support"] == 0
    assert metrics["skill_status_accuracy"] == 0


def test_matching_keyword_remains_semantically_unreviewed():
    case = load_dataset().cases[0]
    run = make_run(case, [Prediction(skill="Python", status="supported", citations=[Citation(source=case.resume, quote="Python")])])
    metrics = evaluate(case, run)
    assert metrics["evidence_validity"] == 1
    assert metrics["semantic_review_coverage"] == 0 and metrics["semantic_positive_support"] is None


@pytest.mark.parametrize("status,expected", [("supported", 0), ("partial", 1)])
def test_partial_gold_evidence_cannot_support_full_claim(status, expected):
    case = load_dataset().cases[4]
    run = make_run(case, [Prediction(skill="SQL", status=status, citations=[ref(case.gold[0].evidence[1])])])
    assert evaluate(case, run)["semantic_positive_support"] == expected


def test_single_scope_does_not_include_authorized_supplements():
    case = load_dataset().cases[1]
    run = make_run(case, [Prediction(skill="RAG", status="supported", citations=[ref(case.gold[0].evidence[0])])])
    assert evaluate(case, run)["evidence_validity"] == 1
    run.method = "single"
    assert evaluate(case, run)["evidence_validity"] == 0


def test_empty_denominators_are_unavailable_not_perfect():
    case = load_dataset().cases[6]
    metrics = evaluate(case, make_run(case, [Prediction(skill="RAG", status="not_found")]))
    assert metrics["evidence_validity"] is metrics["useful_retrieval_rate"] is metrics["semantic_positive_support"] is None
    assert metrics["skill_status_accuracy"] == 1


def test_useful_retrieval_counts_new_relevant_spans_not_duplicates_or_failures():
    from src.evidence_search import ProjectEvidenceSearch
    case = load_dataset().cases[1]
    result = ProjectEvidenceSearch(case.authorized_sources).search_project_evidence("RAG", case.authorized_sources[1])
    attempt = {"skill": "RAG", "source": case.authorized_sources[1], "success": True,
               "candidates": [item.model_dump() for item in result.candidates]}
    run = make_run(case, [])
    run.retrievals = [attempt, attempt, {**attempt, "success": False, "candidates": []}]
    metrics = evaluate(case, run)
    assert metrics["useful_retrievals"] == 1 and metrics["retrieval_attempts"] == 3
    assert metrics["useful_retrieval_rate"] == pytest.approx(1 / 3)


def test_raw_score_changes_do_not_affect_status_accuracy():
    case = load_dataset().cases[6]
    run = make_run(case, [Prediction(skill="RAG", status="supported")], score=100)
    assert evaluate(case, run)["skill_status_accuracy"] == 0


def test_completion_waiting_and_error_are_separate_and_micro_aggregated():
    case = load_dataset().cases[6]
    runs = [make_run(case, [Prediction(skill="RAG", status="not_found")]) for _ in range(3)]
    runs[1].status, runs[2].status = "waiting_for_user", "tool_error"
    stats = aggregate([(run, evaluate(case, run)) for run in runs])
    assert stats["task_completion_rate"] == stats["waiting_rate"] == stats["error_rate"] == pytest.approx(1/3)
    assert stats["status_counts"] == {"finished": 1, "tool_error": 1, "waiting_for_user": 1}
    assert stats["llm_requests"] == 3 and stats["token_usage"]["total_tokens"] is None


def test_invalid_actions_not_double_counted_as_termination():
    case = load_dataset().cases[6]
    run = make_run(case, [], trace=[{"event": "decision", "error_code": "invalid_target"},
        {"event": "search", "error_code": "duplicate_search"}, {"event": "termination", "error_code": "duplicate_search"}])
    metrics = evaluate(case, run)
    assert metrics["invalid_actions"] == 2 and metrics["duplicate_actions"] == 1
