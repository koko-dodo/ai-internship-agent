
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator


class CandidateProfile(BaseModel):
    """Structured candidate profile."""

    education: str = ""
    skills: list[str] = Field(default_factory=list)
    projects: list[str] = Field(default_factory=list)
    experience: list[str] = Field(default_factory=list)


class JobPosting(BaseModel):
    """Structured job posting."""

    title: str
    company: str = ""
    required_skills: list[str] = Field(default_factory=list)
    preferred_skills: list[str] = Field(default_factory=list)
    description: str = ""


class MatchResult(BaseModel):
    """Structured job matching result."""

    job_title: str
    score: float = Field(ge=0, le=100)
    matched_skills: list[str] = Field(default_factory=list)
    missing_skills: list[str] = Field(default_factory=list)
    reasoning: str = ""


class ToolArguments(BaseModel):
    """Never coerce input types or silently ignore unknown fields."""

    model_config = ConfigDict(strict=True, extra="forbid")


class ReadResumeArguments(ToolArguments):
    file_path: str = Field(min_length=1)

    @field_validator("file_path")
    @classmethod
    def nonblank_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("file_path must not be blank")
        return value


class ParseJobArguments(ToolArguments):
    jd_text: str = Field(min_length=1)

    @field_validator("jd_text")
    @classmethod
    def nonblank_jd(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("jd_text must not be blank")
        return value


class FindEvidenceArguments(ToolArguments):
    resume_text: str
    skills: list[str]

    @field_validator("skills")
    @classmethod
    def nonblank_skills(cls, value: list[str]) -> list[str]:
        if any(not skill.strip() for skill in value):
            raise ValueError("skills must contain nonblank keywords")
        return [skill.strip() for skill in value]


class SkillEvidence(BaseModel):
    skill: str
    found: bool
    evidence: list[str] = Field(default_factory=list)


class ToolError(BaseModel):
    code: str
    message: str


class ToolResult(BaseModel):
    tool_name: str
    success: bool
    data: Any = None
    error: ToolError | None = None
