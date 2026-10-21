import hashlib
import json

import pytest
from pydantic import ValidationError

from src.llm import LLMResponse, MockLLMClient
from src.matching import (
    EvidenceBasedMatcher, MatchingModelError, build_match_report, normalize_job,
    score_matches, validate_quote,
)
from src.schemas import (
    EvidenceSkillMatch, JobPosting, ScoringWeights, SemanticEvidenceEvaluation,
    SkillMatchState,
)


def assessment(skill="Python", status="supported", quotes=None):
    return {"skill": skill, "status": status, "quotes": quotes or [], "reasoning": "模型对技能要求的评估"}


def evaluation(*items):
    return SemanticEvidenceEvaluation.model_validate({"assessments": list(items)})


def make_report(text, *items, required=None, preferred=None):
    return build_match_report(
        JobPosting(title="Intern", required_skills=required or ["Python"], preferred_skills=preferred or []),
        evaluation(*items), text, "resume.md",
    )


def state(skill="Python", status="supported", category="required"):
    return SkillMatchState(skill=skill, status=status, category=category)


def json_response(data):
    return LLMResponse(final_answer=json.dumps(data, ensure_ascii=False))


def job_data(required=None, preferred=None):
    return {"title": "Intern", "company": "Example", "required_skills": required or [], "preferred_skills": preferred or []}


def test_quote_validation_exact_text_lines_and_snapshot():
    text = "# Resume\n\n  Built a Python tool.  \nUsed pytest.\n\nNext section"
    quote = "Python tool.  \nUsed pytest."
    evidence = validate_quote(text, quote, "candidate.md")
    assert len(evidence) == 1
    item = evidence[0]
    assert item.quote == quote
    assert item.start_line == 3 and item.end_line == 4
    assert item.context == "  Built a Python tool.  \nUsed pytest."
    assert item.source == "candidate.md"
    assert item.resume_sha256 == hashlib.sha256(text.encode()).hexdigest()


@pytest.mark.parametrize("quote", ["", "  ", "built python", "Built a Rust tool", "Python...pytest"])
def test_quotes_are_not_fuzzy_matched_or_repaired(quote):
    assert validate_quote("Built a Python tool and pytest tests.", quote, "resume.txt") == []


def test_repeated_and_overlapping_quotes_get_all_source_locations():
    assert [item.start_line for item in validate_quote("Python\nPython", "Python", "r.md")] == [1, 2]
    assert len(validate_quote("banana", "ana", "r.md")) == 2


def test_verified_supported_evidence_gets_full_credit():
    text = "Built a Python reporting service."
    report = make_report(text, assessment(quotes=[text]))
    assert report.skills[0].status == "supported"
    assert report.skills[0].evidence[0].quote == text
    assert report.score.score == 100
    assert report.score.applicable
    assert report.resume_source == "resume.md"


def test_not_found_is_not_a_statement_of_inability():
    report = make_report("Only education listed", assessment(status="not_found"))
    assert report.skills[0].status == "not_found"
    assert report.skills[0].evidence == []
    assert report.score.score == 0
    assert "不代表候选人没有" in report.caveat
    assert report.needs_verification


def test_partial_has_half_credit_and_real_source():
    text = "Completed a Python basic tutorial."
    report = make_report(text, assessment(status="partial", quotes=[text]))
    assert report.skills[0].status == "partial"
    assert report.score.score == 50


@pytest.mark.parametrize("status", ["supported", "partial"])
@pytest.mark.parametrize("quotes", [[], ["Made up a Python project"], [" "]])
def test_missing_or_fabricated_evidence_cannot_earn_credit(status, quotes):
    report = make_report("Only education listed", assessment(status=status, quotes=quotes))
    assert report.skills[0].status == "uncertain"
    assert report.skills[0].evidence == []
    assert report.score.score == 0
    assert report.skills[0].validation_notes
    assert "Made up" not in report.model_dump_json()


def test_mixed_real_and_fake_quotes_are_conservatively_downgraded():
    text = "Python project"
    report = make_report(text, assessment(quotes=[text, "Fake advanced production experience"]))
    assert report.skills[0].status == "uncertain"
    assert len(report.skills[0].evidence) == 1
    assert report.score.score == 0


@pytest.mark.parametrize("text, quote", [
    ("I have never used Python.", "Python"),
    ("我不会Python。", "Python"),
    ("尚未使用 Python 做过项目。", "Python"),
    ("No experience with Python", "Python"),
    ("没有使用 Python\n这是目前的学习计划。", "Python"),
])
def test_negation_is_checked_in_full_context_not_cherry_picked_quote(text, quote):
    report = make_report(text, assessment(quotes=[quote]))
    assert report.skills[0].status == "uncertain"
    assert report.score.score == 0
    assert report.skills[0].evidence  # Authentic negative context remains inspectable.
    assert report.skills[0].evidence[0].context == text


def test_contradictory_other_mentions_cannot_be_hidden_by_positive_quote():
    text = "Built a Python project.\n\nNever used:\nPython"
    report = make_report(text, assessment(quotes=["Built a Python project."]))
    assert report.skills[0].status == "uncertain"
    assert report.score.score == 0


@pytest.mark.parametrize("text", [
    "Python 入门课程", "Completed Python basics.", "Python beginner tutorial", "仅了解 Python",
])
def test_basic_learning_cannot_be_scored_as_full_match(text):
    report = make_report(text, assessment(quotes=[text]))
    assert report.skills[0].status == "partial"
    assert report.score.score == 50


def test_duplicate_quotes_do_not_duplicate_evidence():
    report = make_report("Python project", assessment(quotes=["Python project", "Python project"]))
    assert len(report.skills[0].evidence) == 1


def test_missing_assessment_is_uncertain_and_cannot_shrink_denominator():
    report = make_report("Python project", assessment(quotes=["Python project"]), required=["Python", "SQL"])
    assert [item.status for item in report.skills] == ["supported", "uncertain"]
    assert report.score.score == 50


@pytest.mark.parametrize("items", [
    [assessment("Rust", "not_found")],
    [assessment("Python", "not_found"), assessment("python", "supported")],
])
def test_unknown_or_duplicate_model_assessments_are_rejected(items):
    with pytest.raises(MatchingModelError):
        make_report("Python", *items)


def test_job_normalization_deduplicates_categories_and_aliases():
    job = normalize_job(JobPosting(
        title="Intern", required_skills=[" python ", "PYTHON", "sklearn"],
        preferred_skills=["Python", "scikit-learn", " Git ", "git"], description="original",
    ))
    assert job.required_skills == ["Python", "scikit-learn"]
    assert job.preferred_skills == ["Git"]
    assert job.description == "original"


def test_report_has_one_match_per_deduplicated_requirement():
    report = make_report("Python project", assessment(quotes=["Python project"]),
                         required=["Python", "python"], preferred=["PYTHON"])
    assert len(report.skills) == 1
    assert report.skills[0].category == "required"
    assert report.score.score == 100


def test_required_skills_have_double_preferred_weight_by_default():
    required_hit = score_matches([state(), state("Docker", "not_found", "preferred")])
    preferred_hit = score_matches([state(status="not_found"), state("Docker", "supported", "preferred")])
    assert required_hit.score == 66.67
    assert preferred_hit.score == 33.33
    assert required_hit.weights.required == 2.0
    custom = score_matches([state(), state("Docker", "not_found", "preferred")], ScoringWeights(required=3.0))
    assert custom.score == 75


@pytest.mark.parametrize("status, expected", [("supported", 100), ("partial", 50), ("not_found", 0), ("uncertain", 0)])
def test_score_boundaries_and_each_status(status, expected):
    result = score_matches([state(status=status)])
    assert result.score == expected
    assert 0 <= result.score <= 100


def test_no_skill_requirements_has_no_applicable_score():
    report = build_match_report(JobPosting(title="Intern"), evaluation(), "Resume", "r.txt")
    assert report.skills == []
    assert report.score.score == 0
    assert report.score.applicable is False
    assert report.score.total_weight == 0
    assert "不适用" in report.analysis


def test_scoring_duplicate_states_is_order_independent_and_conservative():
    duplicate = [state("python"), state("Python", category="preferred")]
    assert score_matches(duplicate).score == 100
    assert score_matches(duplicate).total_weight == score_matches([state()]).total_weight
    conflict = [state(), state("PYTHON", "not_found", "preferred")]
    assert score_matches(conflict).score == score_matches(conflict[::-1]).score == 0


def test_scoring_never_accepts_a_model_supplied_numeric_score():
    with pytest.raises(TypeError):
        score_matches([{"skill": "Python", "status": "supported", "score": 100}])
    with pytest.raises(ValidationError):
        SemanticEvidenceEvaluation.model_validate({"assessments": [], "score": 100})
    with pytest.raises(ValidationError):
        score_matches([SkillMatchState.model_construct(skill="Python", category="required", status="perfect")])


@pytest.mark.parametrize("weight", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_scoring_weights_are_rejected(weight):
    with pytest.raises(ValidationError):
        ScoringWeights(required=weight)


def test_finite_extreme_weights_stay_in_score_bounds():
    weights = ScoringWeights(required=1e308, preferred=5e-324)
    assert score_matches([state()], weights).score == 100
    assert score_matches([state(category="preferred")], weights).score == 100


def test_positive_report_schema_requires_evidence():
    with pytest.raises(ValidationError):
        EvidenceSkillMatch(skill="Python", category="required", status="supported", evidence=[], reasoning="unverified")


def test_matcher_semantic_calls_receive_original_data_and_no_tools(tmp_path):
    path = tmp_path / "candidate.md"
    path.write_text("Python project", encoding="utf-8")
    mock = MockLLMClient([
        json_response(job_data(["Python", "python"])),
        json_response({"assessments": [assessment(quotes=["Python project"])]}),
    ])
    jd = "岗位：语义数据开发实习生；需要 Python。"
    report = EvidenceBasedMatcher(mock, str(path), jd, allowed_directory=tmp_path).match()
    assert report.job.description == jd
    assert report.job.required_skills == ["Python"]
    assert report.resume_source == "candidate.md"
    assert report.score.score == 100
    assert len(mock.requests) == 2
    assert all(request.tools == [] for request in mock.requests)
    assert jd in mock.requests[0].messages[0].content
    assert "Python project" in mock.requests[1].messages[0].content


def test_no_skills_skips_evaluation_request(tmp_path):
    path = tmp_path / "r.txt"
    path.write_text("Resume", encoding="utf-8")
    mock = MockLLMClient([json_response(job_data())])
    report = EvidenceBasedMatcher(mock, str(path), "Intern", allowed_directory=tmp_path).match()
    assert not report.score.applicable
    assert len(mock.requests) == 1


@pytest.mark.parametrize("response", [
    "PRIVATE_NOT_JSON", "```json\n{}\n```", "[]", "{}",
    '{"title":"Intern","required_skills":[],"preferred_skills":[],"score":100}',
    '{"title":"First","title":"Second","required_skills":[],"preferred_skills":[]}',
    '{"title":"Intern","required_skills":[123],"preferred_skills":[]}',
    '{"title":"Intern","required_skills":[" "],"preferred_skills":[]}',
])
def test_malformed_semantic_job_output_fails_without_echoing_data(tmp_path, response):
    path = tmp_path / "r.txt"
    path.write_text("PRIVATE_RESUME", encoding="utf-8")
    mock = MockLLMClient([LLMResponse(final_answer=response)])
    with pytest.raises(MatchingModelError) as caught:
        EvidenceBasedMatcher(mock, str(path), "Intern", allowed_directory=tmp_path).match()
    assert "PRIVATE" not in str(caught.value)
    assert len(mock.requests) == 1


@pytest.mark.parametrize("evaluation_data", [
    {"assessments": [{**assessment(), "status": "perfect"}]},
    {"assessments": [{**assessment(), "quotes": "Python"}]},
    {"assessments": [assessment()], "score": 100},
    {"assessments": [{**assessment(), "source": "/invented/path"}]},
])
def test_invalid_evaluation_schema_fails(tmp_path, evaluation_data):
    path = tmp_path / "r.txt"
    path.write_text("Python", encoding="utf-8")
    mock = MockLLMClient([json_response(job_data(["Python"])), json_response(evaluation_data)])
    with pytest.raises(MatchingModelError):
        EvidenceBasedMatcher(mock, str(path), "Intern", allowed_directory=tmp_path).match()


@pytest.mark.parametrize("kind, exception", [("outside", PermissionError), ("missing", FileNotFoundError), ("symlink", PermissionError)])
def test_matching_reads_only_authorized_resume_and_never_calls_model_on_file_error(tmp_path, kind, exception):
    root = tmp_path / "allowed"
    root.mkdir()
    outside = tmp_path / "outside.txt"
    outside.write_text("private", encoding="utf-8")
    path = root / "missing.txt" if kind == "missing" else outside
    if kind == "symlink":
        path = root / "link.txt"
        path.symlink_to(outside)
    mock = MockLLMClient([])
    with pytest.raises(exception):
        EvidenceBasedMatcher(mock, str(path), "Intern", allowed_directory=root).match()
    assert mock.requests == []
