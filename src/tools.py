
"""Offline tools with constrained file access and explicit text rules."""

import re
from pathlib import Path

from .schemas import (
    FindEvidenceArguments,
    JobPosting,
    ParseJobArguments,
    ReadResumeArguments,
    SkillEvidence,
)

DEFAULT_RESUME_DIRECTORY = Path(__file__).resolve().parent.parent / "examples"

# Canonical names and literal aliases; this is not semantic inference.
SKILL_ALIASES = {
    "Python": ("python",),
    "SQL": ("sql",),
    "Git": ("git",),
    "Linux": ("linux",),
    "Docker": ("docker",),
    "Java": ("java",),
    "JavaScript": ("javascript",),
    "TypeScript": ("typescript",),
    "C++": ("c++",),
    "C#": ("c#",),
    "PyTorch": ("pytorch",),
    "TensorFlow": ("tensorflow",),
    "Pandas": ("pandas",),
    "NumPy": ("numpy",),
    "scikit-learn": ("scikit-learn", "sklearn"),
    "Machine Learning": ("machine learning", "机器学习"),
    "Deep Learning": ("deep learning", "深度学习"),
    "NLP": ("nlp", "自然语言处理"),
    "LLM": ("llm", "llms", "大语言模型"),
}


def _contains_keyword(text: str, keyword: str) -> bool:
    """Case-insensitive literal matching with ASCII token boundaries."""
    escaped = re.escape(keyword)
    if keyword.isascii():
        # Allow English skills adjacent to Chinese prose, but not SQL in MySQL.
        escaped = rf"(?<![A-Za-z0-9_]){escaped}(?![A-Za-z0-9_])"
    return re.search(escaped, text, flags=re.IGNORECASE) is not None


def read_resume(
    file_path: str, *, allowed_directory: str | Path = DEFAULT_RESUME_DIRECTORY
) -> str:
    """Read UTF-8 TXT/MD inside allowed_directory; relative paths use cwd.

    Resolve traversal and symlinks before checking containment. The directory
    is trusted application configuration, never a tool-call argument.
    """
    args = ReadResumeArguments(file_path=file_path)
    root = Path(allowed_directory).resolve(strict=True)
    if not root.is_dir():
        raise ValueError("Allowed resume directory must be a directory")
    path = Path(args.file_path).resolve()
    if not path.is_relative_to(root):
        raise PermissionError("Resume path is outside the allowed directory")
    if path.suffix.lower() not in {".txt", ".md"}:
        raise ValueError("Unsupported file format. Use .txt or .md.")
    if not path.is_file():
        raise FileNotFoundError("Resume file not found")
    return path.read_text(encoding="utf-8")


def parse_job(jd_text: str) -> JobPosting:
    """Extract labeled metadata and fixed vocabulary skills using line rules.

    Unlabeled mentions default to required. Preferred sections persist until
    a required/responsibilities heading. No negation or proficiency inference.
    """
    args = ParseJobArguments(jd_text=jd_text)
    title = ""
    company = ""
    required: list[str] = []
    preferred: list[str] = []
    section = "required"
    for raw_line in args.jd_text.splitlines():
        line = raw_line.strip().lstrip("#*- ").strip()
        if not line:
            continue
        metadata = re.match(
            r"^(title|job title|职位|岗位|职位名称|company|公司|公司名称)\s*[:：]\s*(.+)$",
            line, flags=re.IGNORECASE,
        )
        if metadata:
            label, value = metadata.groups()
            if label.lower() in {"company", "公司", "公司名称"}:
                company = value.strip()
            else:
                title = value.strip()
            continue
        if not title:
            title = line
        if re.match(
            r"^(preferred(?: qualifications| skills)?|nice[- ]to[- ]have|bonus|加分项|优先条件|优先)(?:\s*[:：]|\s*$)",
            line, flags=re.IGNORECASE,
        ):
            section = "preferred"
        elif re.match(
            r"^(required(?: qualifications| skills)?|requirements|qualifications|responsibilities|任职要求|岗位要求|必备技能|工作职责|职责)(?:\s*[:：]|\s*$)",
            line, flags=re.IGNORECASE,
        ):
            section = "required"
        destination = preferred if section == "preferred" else required
        for skill, aliases in SKILL_ALIASES.items():
            if any(_contains_keyword(line, alias) for alias in aliases):
                if skill not in destination:
                    destination.append(skill)
    # Explicit required mentions win over preferred mentions.
    preferred = [skill for skill in preferred if skill not in required]
    return JobPosting(
        title=title, company=company, required_skills=required,
        preferred_skills=preferred, description=jd_text,
    )


def find_evidence(resume_text: str, skills: list[str]) -> list[SkillEvidence]:
    """Return exact original lines for each skill; do not expand aliases.

    A hit proves only a textual mention, not ability or experience.
    """
    args = FindEvidenceArguments(resume_text=resume_text, skills=skills)
    lines = args.resume_text.splitlines()
    result = []
    for skill in args.skills:
        evidence = [line for line in lines if _contains_keyword(line, skill)]
        result.append(SkillEvidence(skill=skill, found=bool(evidence), evidence=evidence))
    return result
