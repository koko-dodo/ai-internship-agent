"""Load manual labels and authorize individual fixture files before reading."""

import hashlib
import json
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from src.evidence_search import EXAMPLES_DIRECTORY, ProjectEvidenceSearch
from src.matching import canonical_skill, validate_quote
from src.schemas import MatchStatus, NonblankText
from src.tools import read_resume


class Record(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)


class Citation(Record):
    source: NonblankText
    # Preserve even empty/whitespace model quotes for auditing; never repair
    # Single LLM's raw evidence by stripping it into an apparent exact match.
    quote: str
    start_line: int | None = Field(default=None, ge=1)
    end_line: int | None = Field(default=None, ge=1)
    resume_sha256: str | None = None


class GoldEvidence(Citation):
    quote: str = Field(min_length=1)
    start_line: int = Field(ge=1)
    end_line: int = Field(ge=1)
    # Keep draft vocabulary compatible; add explicit limitation and denial.
    relation: Literal["supports", "partial", "contradicts", "irrelevant", "limits", "negates"]


class GoldSkill(Record):
    skill: NonblankText
    category: Literal["required", "preferred"]
    status: MatchStatus
    rationale: NonblankText
    evidence: list[GoldEvidence]


class Case(Record):
    id: str = Field(pattern=r"^\d{2}$")
    scenario: NonblankText
    resume: NonblankText
    jd: NonblankText
    authorized_sources: list[NonblankText]
    gold: list[GoldSkill] = Field(min_length=1)
    user_reply: NonblankText | None
    fault: Literal["access_denied", "io_error"] | None

    @model_validator(mode="after")
    def distinct_targets(self):
        keys = [canonical_skill(item.skill).casefold() for item in self.gold]
        if len(keys) != len(set(keys)) or len(self.authorized_sources) != len(set(self.authorized_sources)):
            raise ValueError("Duplicate skills or grants")
        if self.resume in self.authorized_sources or self.jd in self.authorized_sources:
            raise ValueError("Supplemental files must differ from inputs")
        for item in self.gold:
            relations = {ref.relation for ref in item.evidence}
            if item.status == "supported" and "supports" not in relations:
                raise ValueError("Supported gold requires a reviewed supporting excerpt")
            if item.status == "partial" and not relations.intersection({"supports", "partial"}):
                raise ValueError("Partial gold requires a reviewed practice excerpt")
        return self


class Dataset(Record):
    version: NonblankText
    provenance: NonblankText
    status_definitions: dict[str, str]
    cases: list[Case]

    @model_validator(mode="after")
    def unique_cases(self):
        if len({case.id for case in self.cases}) != len(self.cases):
            raise ValueError("Duplicate case IDs")
        if set(self.status_definitions) != {"supported", "partial", "not_found", "uncertain"}:
            raise ValueError("All four status definitions are required")
        return self


def read_source(source: str) -> str:
    # Reuse the stricter project grant policy for resume/JD as well: no hidden
    # paths, traversal, external symlinks, broad directories or oversized files.
    grant = ProjectEvidenceSearch([source], max_searches=0)
    normalized = grant.offers()[0]["source"]
    if normalized != source:
        raise ValueError("Dataset sources must use canonical examples-relative paths")
    return read_resume(str(EXAMPLES_DIRECTORY / source), allowed_directory=EXAMPLES_DIRECTORY)


def documents(case: Case, *, supplements=True) -> dict[str, str]:
    sources = [case.resume] + (case.authorized_sources if supplements else [])
    return {source: read_source(source) for source in sources}


def citation_locations(citation: Citation, texts: dict[str, str]):
    text = texts.get(citation.source)
    if text is None:
        return []
    return [ref for ref in validate_quote(text, citation.quote, citation.source)
            if (citation.start_line is None or citation.start_line == ref.start_line)
            and (citation.end_line is None or citation.end_line == ref.end_line)
            and (citation.resume_sha256 is None or citation.resume_sha256 == ref.resume_sha256)]


def load_dataset(path: Path | None = None) -> Dataset:
    path = path or Path(__file__).with_name("cases.json")
    if path.suffix != ".json" or path.name.startswith("."):
        raise ValueError("Only a JSON dataset manifest is accepted")
    dataset = Dataset.model_validate_json(path.read_text(encoding="utf-8"))
    for case in dataset.cases:
        read_source(case.jd)
        texts = documents(case)
        for skill in case.gold:
            for citation in skill.evidence:
                if not citation_locations(citation, texts):
                    raise ValueError("Gold evidence must be authorized and correctly located")
    if path.resolve() == Path(__file__).with_name("cases.json").resolve() and dataset.version == "gold-v1":
        verify_gold_freeze(dataset)
    return dataset


def dataset_fingerprint(dataset: Dataset) -> str:
    payload = {"manifest": dataset.model_dump(), "files": {
        source: read_source(source) for case in dataset.cases
        for source in [case.resume, case.jd, *case.authorized_sources]
    }}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def gold_files(dataset: Dataset) -> set[str]:
    return {"evaluation/cases.json", "evaluation/GOLD_NOTES.md", "evaluation/GOLD_AUDIT.md",
            "evaluation/GOLD_CHANGELOG.md"} | {
        "examples/" + source for case in dataset.cases
        for source in [case.resume, case.jd, *case.authorized_sources]}


def verify_gold_freeze(dataset: Dataset, *, root: Path | None = None) -> dict:
    """Fail closed on default frozen data drift. Never automatically reseal."""
    root = root or Path(__file__).resolve().parent.parent
    seal = json.loads((root / "evaluation/GOLD_V1_FREEZE.json").read_text(encoding="utf-8"))
    if seal["dataset_version"] != dataset.version or set(seal["sha256"]) != gold_files(dataset):
        raise ValueError("Gold freeze file set/version mismatch")
    for name, digest in seal["sha256"].items():
        path = (root / name).resolve()
        if not path.is_relative_to(root.resolve()) or hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError("Frozen Gold content changed; create a reviewed new version")
    if seal["dataset_fingerprint"] != dataset_fingerprint(dataset):
        raise ValueError("Frozen Gold fingerprint mismatch")
    return seal
