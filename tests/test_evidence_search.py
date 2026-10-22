import hashlib

import pytest

from src import evidence_search
from src.evidence_search import ProjectEvidenceSearch


@pytest.fixture
def root(tmp_path, monkeypatch):
    directory = tmp_path / "examples"
    directory.mkdir()
    monkeypatch.setattr(evidence_search, "EXAMPLES_DIRECTORY", directory)
    return directory


def write(root, name="project.md", text="Built SQL queries."):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def test_search_returns_exact_lines_context_and_source_hash_without_grading(root):
    text = "# Project\n\n  Built SQL queries.  \nUsed JOIN.\n"
    write(root, text=text)
    search = ProjectEvidenceSearch(["project.md"])
    result = search.registry().execute("search_project_evidence", {"skill": "SQL", "source": "project.md"})
    assert result.success
    candidate = result.data["candidates"][0]
    assert candidate["source"] == "project.md"
    assert candidate["line_number"] == 3
    assert candidate["text"] == "  Built SQL queries.  "
    assert "Used JOIN." in candidate["context"]
    assert candidate["sha256"] == hashlib.sha256(text.encode()).hexdigest()
    assert "status" not in candidate
    assert search.search_count == 1
    assert search.offers()[0]["estimated_read_units"] == 1


@pytest.mark.parametrize("source", ["../private.txt", "/private/file.txt", ".env", "ungranted.md", "folder/../../private.md"])
def test_unlisted_paths_are_denied_without_reading(root, monkeypatch, source):
    write(root)
    search = ProjectEvidenceSearch(["project.md"])
    def forbidden(*args, **kwargs):
        raise AssertionError("No file read is permitted")
    monkeypatch.setattr(evidence_search, "read_resume", forbidden)
    result = search.registry().execute("search_project_evidence", {"skill": "SQL", "source": source})
    assert result.error.code == "access_denied"
    assert search.search_count == 0


@pytest.mark.parametrize("kind", ["outside", "traversal", "hidden", "format", "symlink"])
def test_manifest_cannot_authorize_outside_hidden_or_unsupported_paths(root, tmp_path, kind):
    outside = tmp_path / "outside.txt"
    outside.write_text("dummy", encoding="utf-8")
    sources = {
        "outside": outside,
        "traversal": root / ".." / "outside.txt",
        "hidden": root / ".private.md",
        "format": root / "project.pdf",
        "symlink": root / "escape.md",
    }
    if kind == "symlink":
        sources[kind].symlink_to(outside)
    with pytest.raises(PermissionError):
        ProjectEvidenceSearch([sources[kind]])


def test_authorization_is_explicit_per_file_and_atomic(root):
    write(root)
    search = ProjectEvidenceSearch([])
    with pytest.raises(PermissionError):
        search.authorize(["project.md", ".env"])
    assert search.offers() == []
    search.authorize(["project.md"])
    assert len(search.offers()) == 1


def test_internal_symlink_does_not_create_a_second_search_identity(root):
    target = write(root)
    (root / "alias.md").symlink_to(target)
    search = ProjectEvidenceSearch(["project.md", "alias.md"])
    assert [offer["source"] for offer in search.offers()] == ["project.md"]
    search.search_project_evidence("SQL", "project.md")
    with pytest.raises(ValueError, match="Duplicate"):
        search.search_project_evidence("sql", "project.md")
    assert search.search_count == 1


def test_file_replaced_with_external_symlink_is_denied(root, tmp_path):
    path = write(root)
    search = ProjectEvidenceSearch(["project.md"])
    outside = tmp_path / "outside.txt"
    outside.write_text("dummy", encoding="utf-8")
    path.unlink()
    path.symlink_to(outside)
    result = search.registry().execute("search_project_evidence", {"skill": "SQL", "source": "project.md"})
    assert result.error.code == "access_denied"
    assert search.search_count == 0


def test_alias_skill_duplicate_is_rejected_even_without_hits(root):
    write(root, text="No matching information.")
    search = ProjectEvidenceSearch(["project.md"])
    assert not search.search_project_evidence("sklearn", "project.md").candidates
    with pytest.raises(ValueError, match="Duplicate"):
        search.search_project_evidence("scikit-learn", "project.md")
    assert search.search_count == 1


def test_distinct_skills_can_search_the_same_file_but_never_exceed_three(root):
    write(root)
    search = ProjectEvidenceSearch(["project.md"])
    for skill in ["SQL", "Git", "Docker"]:
        search.search_project_evidence(skill, "project.md")
    with pytest.raises(ValueError, match="limit"):
        search.search_project_evidence("Python", "project.md")
    assert search.search_count == 3


def test_snapshots_are_immutable_per_file_skill_search(root):
    path = write(root, text="SQL original project.")
    search = ProjectEvidenceSearch(["project.md"])
    search.search_project_evidence("SQL", "project.md")
    path.write_text("Changed material", encoding="utf-8")
    assert search.snapshots_for("SQL") == {"project.md": "SQL original project."}
    assert search.snapshots_for("Git") == {}


@pytest.mark.parametrize("limit", [-1, 4, True, "3"])
def test_invalid_search_limit(limit):
    with pytest.raises(ValueError):
        ProjectEvidenceSearch([], max_searches=limit)


def test_file_size_limit_and_no_directory_scan(root):
    write(root, text="x" * (64 * 1024 + 1))
    with pytest.raises(ValueError, match="64 KiB"):
        ProjectEvidenceSearch(["project.md"])
    with pytest.raises(PermissionError):
        ProjectEvidenceSearch([root])


def test_search_arguments_use_strict_registry_validation(root):
    write(root)
    search = ProjectEvidenceSearch(["project.md"])
    for arguments in [{}, {"skill": 123, "source": "project.md"}, {"skill": "SQL", "source": "project.md", "root": "/"}]:
        assert search.registry().execute("search_project_evidence", arguments).error.code == "invalid_arguments"
    assert search.search_count == 0


@pytest.mark.parametrize("skill", ["SQL", "SQL查询", "SQL 查询", "SQL queries", "sql QUERIES", "SQL query optimization"])
def test_real_project_material_is_retrieved_for_skill_phrases(skill):
    search = ProjectEvidenceSearch(["projects/sql_project.md"])
    result = search.registry().execute("search_project_evidence", {"skill": skill, "source": "projects/sql_project.md"})
    assert result.success
    assert len(result.data["candidates"]) == 1
    hit = result.data["candidates"][0]
    assert hit["line_number"] == 3
    assert hit["text"] == "本人负责 SQL 查询模块，使用 JOIN 和 GROUP BY 汇总借阅记录，"
    assert "status" not in hit  # Broader recall must not confer skill credit.


@pytest.mark.parametrize("skill, text", [
    ("Python开发", "Built a Python application."),
    ("Python programming", "Built a Python application."),
    ("JavaScript开发", "Built a JavaScript application."),
    ("机器学习项目", "Applied machine learning to a dataset."),
    ("C++ development", "Built a C++ application."),
    ("advanced sklearn usage", "Used scikit-learn for classification."),
])
def test_skill_phrase_recall_is_not_sql_specific(root, skill, text):
    write(root, text=text)
    result = ProjectEvidenceSearch(["project.md"]).search_project_evidence(skill, "project.md")
    assert len(result.candidates) == 1
    assert result.candidates[0].text == text


@pytest.mark.parametrize("skill, text", [
    ("SQL查询", "Used MySQL, NoSQL and SQLite."),
    ("MySQL queries", "Used SQL."),
    ("Java development", "Built a JavaScript application."),
    ("JavaScript开发", "Built a Java application."),
    ("Git usage", "Created a GitHub account."),
    ("Pythonic design", "Used Python."),
    ("unknown specialty", "An unknown technology."),
])
def test_phrase_recall_respects_token_boundaries_and_unknown_fallback(root, skill, text):
    write(root, text=text)
    assert not ProjectEvidenceSearch(["project.md"]).search_project_evidence(skill, "project.md").candidates


def test_unknown_phrase_retains_literal_search(root):
    write(root, text="Worked on unknown specialty.")
    assert ProjectEvidenceSearch(["project.md"]).search_project_evidence("unknown specialty", "project.md").candidates


@pytest.mark.parametrize("first, second", [("SQL", "SQL查询"), ("SQL查询", "SQL queries"), ("SQL queries", "SQL 查询")])
def test_equivalent_retrieval_phrases_share_duplicate_keys_and_snapshots(root, monkeypatch, first, second):
    write(root)
    search = ProjectEvidenceSearch(["project.md"])
    search.search_project_evidence(first, "project.md")
    assert search.already_searched("project.md", second)
    assert search.snapshots_for(second) == {"project.md": "Built SQL queries."}
    monkeypatch.setattr(evidence_search, "read_resume", lambda *args, **kwargs: pytest.fail("Duplicate must not reread"))
    with pytest.raises(ValueError, match="Duplicate"):
        search.search_project_evidence(second, "project.md")
    assert search.search_count == 1


def test_multi_skill_phrase_keeps_each_token_in_its_search_identity(root):
    write(root, text="Used SQL and Python.")
    search = ProjectEvidenceSearch(["project.md"])
    search.search_project_evidence("SQL查询", "project.md")
    assert not search.already_searched("project.md", "SQL and Python development")
    search.search_project_evidence("SQL and Python development", "project.md")
    assert search.already_searched("project.md", "Python / SQL")
    assert search.search_count == 2
