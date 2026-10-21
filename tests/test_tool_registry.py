import json

import pytest
from pydantic import BaseModel

from src.schemas import ParseJobArguments
from src.tool_registry import ToolRegistry, create_tool_registry


def test_registry_executes_all_tools_with_uniform_json_results(tmp_path):
    path = tmp_path / "resume.md"
    path.write_text("  Python project  \n", encoding="utf-8")
    registry = create_tool_registry(tmp_path)
    resume = registry.execute("read_resume", {"file_path": str(path)})
    job = registry.execute("parse_job", {"jd_text": "AI Intern\nRequired: Python, SQL"})
    evidence = registry.execute(
        "find_evidence", {"resume_text": resume.data, "skills": job.data["required_skills"]}
    )
    for result in [resume, job, evidence]:
        assert result.success is True
        assert result.error is None
        assert json.loads(result.model_dump_json())["success"] is True
    assert evidence.data == [
        {"skill": "Python", "found": True, "evidence": ["  Python project  "]},
        {"skill": "SQL", "found": False, "evidence": []},
    ]


def test_registry_requires_explicit_registration():
    registry = ToolRegistry()
    result = registry.execute("parse_job", {"jd_text": "Intern"})
    assert not result.success
    assert result.data is None
    assert result.error.code == "unknown_tool"
    assert registry.execute("__import__", {}).error.code == "unknown_tool"


@pytest.mark.parametrize(
    "name, arguments",
    [
        ("read_resume", {}),
        ("read_resume", {"file_path": 123}),
        ("read_resume", {"file_path": "  "}),
        ("read_resume", {"file_path": "x.txt", "allowed_directory": "/"}),
        ("parse_job", {"jd_text": "Python", "extra": True}),
        ("parse_job", {"jd_text": None}),
        ("parse_job", {"jd_text": " \n"}),
        ("parse_job", None),
        ("parse_job", '{"jd_text":"Python"}'),
        ("parse_job", []),
        ("find_evidence", {"resume_text": 123, "skills": ["Python"]}),
        ("find_evidence", {"resume_text": "Python", "skills": "Python"}),
        ("find_evidence", {"resume_text": "Python", "skills": [1]}),
        ("find_evidence", {"resume_text": "Python", "skills": [" "]}),
        ("find_evidence", {"resume_text": "Python", "skills": ("Python",)}),
    ],
)
def test_registry_rejects_illegal_arguments(tmp_path, name, arguments):
    result = create_tool_registry(tmp_path).execute(name, arguments)
    assert not result.success
    assert result.data is None
    assert result.error.code == "invalid_arguments"
    assert result.error.message


def test_validation_happens_before_handler_and_does_not_echo_input():
    registry = ToolRegistry()
    calls = []
    registry.register("parse", ParseJobArguments, lambda **kwargs: calls.append(kwargs))
    result = registry.execute("parse", {"jd_text": "private resume", "extra": "private value"})
    assert calls == []
    assert "private resume" not in result.model_dump_json()
    assert "private value" not in result.model_dump_json()


def test_registration_rejects_duplicates_blank_names_and_permissive_models():
    registry = ToolRegistry()
    handler = lambda **kwargs: None
    registry.register("parse", ParseJobArguments, handler)
    with pytest.raises(ValueError, match="already registered"):
        registry.register("parse", ParseJobArguments, handler)
    with pytest.raises(ValueError, match="blank"):
        registry.register(" ", ParseJobArguments, handler)
    with pytest.raises(ValueError, match="forbid"):
        registry.register("loose", BaseModel, handler)


@pytest.mark.parametrize(
    "kind, code",
    [
        ("outside", "access_denied"),
        ("missing", "file_not_found"),
        ("format", "invalid_input"),
        ("encoding", "invalid_encoding"),
    ],
)
def test_registry_returns_explainable_file_errors(tmp_path, kind, code):
    root = tmp_path / "allowed"
    root.mkdir()
    path = (tmp_path if kind == "outside" else root) / (
        "resume.pdf" if kind == "format" else "resume.txt"
    )
    if kind == "encoding":
        path.write_bytes(b"\xff")
    result = create_tool_registry(root).execute("read_resume", {"file_path": str(path)})
    assert result.error.code == code
    assert result.data is None
    assert not result.success


@pytest.mark.parametrize("error, code", [(OSError("private"), "io_error"), (RuntimeError("private"), "execution_error")])
def test_registry_handles_execution_failures(error, code):
    def broken(**kwargs):
        raise error

    registry = ToolRegistry()
    registry.register("broken", ParseJobArguments, broken)
    result = registry.execute("broken", {"jd_text": "Intern"})
    assert result.error.code == code
    assert "private" not in result.model_dump_json()
