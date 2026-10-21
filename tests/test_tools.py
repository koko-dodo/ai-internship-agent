from pathlib import Path

import pytest
from pydantic import ValidationError

from src.schemas import JobPosting
from src.tools import find_evidence, parse_job, read_resume


@pytest.mark.parametrize("suffix", [".txt", ".md", ".TXT", ".MD"])
def test_read_resume_preserves_utf8_text(tmp_path, suffix):
    path = tmp_path / f"resume{suffix}"
    original = "# 简历\n  使用 Python 构建项目。\n"
    path.write_text(original, encoding="utf-8")
    assert read_resume(str(path), allowed_directory=tmp_path) == original


def test_read_resume_default_keeps_existing_relative_interface(monkeypatch):
    project = Path(__file__).resolve().parents[1]
    monkeypatch.chdir(project)
    assert isinstance(read_resume("examples/resume.txt"), str)


def test_read_resume_relative_to_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    path = tmp_path / "resume.txt"
    path.write_text("Python", encoding="utf-8")
    assert read_resume("resume.txt", allowed_directory=tmp_path) == "Python"


@pytest.mark.parametrize("escape", ["absolute", "traversal", "symlink", "prefix"])
def test_read_resume_rejects_directory_escape(tmp_path, escape):
    root = tmp_path / "allowed"
    root.mkdir()
    sibling = tmp_path / "allowed-other"
    sibling.mkdir()
    outside = sibling / "private.txt"
    outside.write_text("private", encoding="utf-8")
    paths = {
        "absolute": outside,
        "traversal": root / ".." / "allowed-other" / "private.txt",
        "prefix": sibling / "private.txt",
        "symlink": root / "link.txt",
    }
    if escape == "symlink":
        paths[escape].symlink_to(outside)
    with pytest.raises(PermissionError):
        read_resume(str(paths[escape]), allowed_directory=root)


def test_read_resume_allows_internal_symlink(tmp_path):
    target = tmp_path / "resume.txt"
    target.write_text("Python", encoding="utf-8")
    link = tmp_path / "link.md"
    link.symlink_to(target)
    assert read_resume(str(link), allowed_directory=tmp_path) == "Python"


@pytest.mark.parametrize("kind", ["unsupported", "missing", "directory", "encoding"])
def test_read_resume_invalid_files(tmp_path, kind):
    path = tmp_path / ("resume.pdf" if kind == "unsupported" else "resume.txt")
    expected = {
        "unsupported": ValueError,
        "missing": FileNotFoundError,
        "directory": FileNotFoundError,
        "encoding": UnicodeDecodeError,
    }[kind]
    if kind == "directory":
        path.mkdir()
    elif kind == "encoding":
        path.write_bytes(b"\xff\xfe")
    elif kind == "unsupported":
        path.write_text("test", encoding="utf-8")
    with pytest.raises(expected):
        read_resume(str(path), allowed_directory=tmp_path)


def test_parse_job_english_sections_and_deduplication():
    text = (
        "# AI Intern\nCompany: Example\nRequired skills:\n"
        "Python, SQL, python\nPreferred qualifications:\nPyTorch, Docker, Python\n"
        "Requirements:\nGit\n"
    )
    job = parse_job(text)
    assert isinstance(job, JobPosting)
    assert job.title == "AI Intern"
    assert job.company == "Example"
    assert job.required_skills == ["Python", "SQL", "Git"]
    assert job.preferred_skills == ["Docker", "PyTorch"]
    assert job.description == text


def test_parse_job_chinese_labels_and_inline_sections():
    job = parse_job(
        "公司：示例公司\n职位：算法实习生\n任职要求：熟悉Python、机器学习、SQL\n"
        "加分项：PyTorch、自然语言处理\n"
    )
    assert job.title == "算法实习生"
    assert job.company == "示例公司"
    assert job.required_skills == ["Python", "SQL", "Machine Learning"]
    assert job.preferred_skills == ["PyTorch", "NLP"]


def test_parse_job_literal_boundaries_and_aliases():
    job = parse_job("Intern\nMySQL, GitHub, JavaScript, C++, C#, sklearn, LLMs")
    assert job.required_skills == ["JavaScript", "C++", "C#", "scikit-learn", "LLM"]


def test_parse_job_does_not_invent_skills_or_company():
    job = parse_job("Research Intern\nAn unfamiliar specialty")
    assert job.title == "Research Intern"
    assert job.company == ""
    assert job.required_skills == job.preferred_skills == []


@pytest.mark.parametrize("text", ["", " \n\t", 123, None])
def test_parse_job_rejects_invalid_input(text):
    with pytest.raises(ValidationError):
        parse_job(text)


def test_find_evidence_returns_exact_lines_and_explicit_absence():
    original = "项目经历\n  使用Python进行分析。  \nBuilt a PYTHON tool.\nSQL reporting\n"
    results = find_evidence(original, ["Python", "Rust", "SQL"])
    assert results[0].found is True
    assert results[0].evidence == ["  使用Python进行分析。  ", "Built a PYTHON tool."]
    assert results[1].skill == "Rust"
    assert results[1].found is False
    assert results[1].evidence == []
    assert results[2].evidence == ["SQL reporting"]


def test_find_evidence_boundaries_and_regex_characters():
    results = find_evidence(
        "MySQL GitHub JavaScript\nC++ and C#\n学习机器学习\nLiteral a.b\naxb",
        ["SQL", "Git", "Java", "C++", "C#", "机器学习", "a.b", ".*"],
    )
    assert [item.found for item in results] == [False, False, False, True, True, True, True, False]
    assert results[6].evidence == ["Literal a.b"]


def test_find_evidence_empty_inputs_and_no_alias_inference():
    assert find_evidence("Python", []) == []
    assert find_evidence("", ["Python"])[0].found is False
    assert find_evidence("机器学习", ["Machine Learning"])[0].found is False


@pytest.mark.parametrize("skills", [[""], ["  "], [123], "Python"])
def test_find_evidence_rejects_invalid_keywords(skills):
    with pytest.raises(ValidationError):
        find_evidence("Python", skills)
