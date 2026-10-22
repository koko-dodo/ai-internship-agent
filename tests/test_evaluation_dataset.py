import json

import pytest
from pydantic import ValidationError

from evaluation.dataset import Case, citation_locations, dataset_fingerprint, documents, load_dataset, read_source


def test_dataset_has_twelve_manual_fictional_cases_with_located_gold():
    dataset = load_dataset()
    assert len(dataset.cases) == 12
    assert {case.id for case in dataset.cases} == {f"{i:02}" for i in range(1, 13)}
    assert "coding assistant" in dataset.provenance
    assert len({case.scenario for case in dataset.cases}) == 12
    for case in dataset.cases:
        texts = documents(case)
        for gold in case.gold:
            assert gold.rationale
            for evidence in gold.evidence:
                assert citation_locations(evidence, texts)


@pytest.mark.parametrize("mutation", [
    lambda case: case["gold"][0].update(status="excellent"),
    lambda case: case["gold"].append(case["gold"][0]),
    lambda case: case["gold"][0].update(evidence=[]),
    lambda case: case["authorized_sources"].append(case["resume"]),
    lambda case: case.update(fault="execute_python"),
])
def test_gold_schema_rejects_invalid_labels(mutation):
    payload = load_dataset().cases[0].model_dump()
    mutation(payload)
    with pytest.raises(ValidationError):
        Case.model_validate(payload)


@pytest.mark.parametrize("field,value", [("quote", "Invented quote"), ("start_line", 900),
                                         ("source", "evaluation/02/b_rag.md"), ("end_line", 1)])
def test_loader_rejects_false_or_wrongly_located_gold(tmp_path, field, value):
    data = load_dataset().model_dump()
    data["cases"][0]["gold"][0]["evidence"][0][field] = value
    manifest = tmp_path / "cases.json"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValueError):
        load_dataset(manifest)


@pytest.mark.parametrize("source", ["../secret.md", ".env", "evaluation/01/../02/resume.md", "/private/tmp/file.md"])
def test_evaluation_file_access_cannot_broaden_examples_grant(source):
    with pytest.raises(PermissionError):
        read_source(source)


def test_symlink_escape_rejected_before_read(tmp_path, monkeypatch):
    from evaluation import dataset
    from src import evidence_search
    root = tmp_path / "examples"
    root.mkdir()
    private = tmp_path / "private.md"
    private.write_text("not authorized")
    (root / "link.md").symlink_to(private)
    monkeypatch.setattr(dataset, "EXAMPLES_DIRECTORY", root)
    monkeypatch.setattr(evidence_search, "EXAMPLES_DIRECTORY", root)
    with pytest.raises(PermissionError):
        read_source("link.md")


def test_dataset_fingerprint_changes_with_annotation_not_runtime_output():
    dataset = load_dataset()
    original = dataset_fingerprint(dataset)
    changed = dataset.model_copy(deep=True)
    changed.cases[0].gold[0].rationale += " Review revision."
    assert dataset_fingerprint(changed) != original
    assert dataset_fingerprint(load_dataset()) == original


def test_duplicate_case_ids_rejected(tmp_path):
    data = load_dataset().model_dump()
    data["cases"].append(data["cases"][0])
    manifest = tmp_path / "cases.json"
    manifest.write_text(json.dumps(data))
    with pytest.raises(ValidationError):
        load_dataset(manifest)
