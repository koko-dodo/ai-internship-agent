"""Explicit-file authorization and bounded literal search, never skill grading."""

import hashlib
from collections.abc import Sequence
from pathlib import Path

from .matching import canonical_skill, validate_quote
from .schemas import ProjectEvidenceCandidate, ProjectSearchResult, SearchProjectEvidenceArguments
from .tool_registry import ToolRegistry
from .tools import SKILL_ALIASES, find_evidence, read_resume


EXAMPLES_DIRECTORY = Path(__file__).resolve().parent.parent / "examples"
MAX_FILE_BYTES = 64 * 1024


def _retrieval_skills(skill: str) -> tuple[str, ...]:
    """Recall known skill tokens inside descriptive phrases, not job equivalence.

    Reuse literal token boundaries: SQL matches SQL查询 / SQL queries, but
    never MySQL or NoSQL. Unknown phrases retain their original literal search.
    """
    name = canonical_skill(skill)
    if name in SKILL_ALIASES:
        return (name,)
    found = tuple(
        name for name, aliases in SKILL_ALIASES.items()
        if any(hit.found for hit in find_evidence(skill, [name, *aliases]))
    )
    return found or (name,)


def project_search_keywords(skill: str) -> list[str]:
    """Retrieval/contradiction-check keywords; never a grading normalization."""
    return list(dict.fromkeys(
        alias for name in _retrieval_skills(skill) for alias in SKILL_ALIASES.get(name, (name,))
    ))


def _skill_key(skill: str) -> tuple[str, ...]:
    return tuple(sorted(name.casefold() for name in _retrieval_skills(skill)))


class ProjectEvidenceSearch:
    """Application code grants individual files, never a directory or glob.

    Relative authorization paths are relative to examples/. No constructor
    parameter can broaden that root. Search state and snapshots survive resume.
    """

    def __init__(self, authorized_sources: Sequence[str | Path], max_searches: int = 3) -> None:
        if type(max_searches) is not int or not 0 <= max_searches <= 3:
            raise ValueError("max_searches must be an integer between 0 and 3")
        self.max_searches = max_searches
        self.search_count = 0
        self._files: dict[str, Path] = {}
        self._snapshots: dict[tuple[str, tuple[str, ...]], str] = {}
        self._searched: set[tuple[str, tuple[str, ...]]] = set()
        self.authorize(authorized_sources)

    def _resolve(self, path: Path) -> Path:
        root = EXAMPLES_DIRECTORY.resolve(strict=True)
        if ".." in path.parts or any(part.startswith(".") for part in path.parts):
            raise PermissionError("Hidden paths and traversal are not authorized")
        resolved = path.resolve()
        if not resolved.is_relative_to(root):
            raise PermissionError("Project material must be inside examples/")
        if any(part.startswith(".") for part in resolved.relative_to(root).parts):
            raise PermissionError("Hidden project material is not authorized")
        if path.suffix.lower() not in {".txt", ".md"} or resolved.suffix.lower() not in {".txt", ".md"}:
            raise PermissionError("Only TXT/Markdown project material is authorized")
        return resolved

    def authorize(self, sources: Sequence[str | Path]) -> None:
        # Atomic grant: a bad entry cannot partially authorize a mixed list.
        additions = {}
        for source in sources:
            path = Path(source)
            path = path if path.is_absolute() else EXAMPLES_DIRECTORY / path
            path = self._resolve(path)
            if not path.is_file():
                raise FileNotFoundError("Authorized project material does not exist")
            if path.stat().st_size > MAX_FILE_BYTES:
                raise ValueError("Project material exceeds the 64 KiB limit")
            additions[path.relative_to(EXAMPLES_DIRECTORY.resolve()).as_posix()] = path
        self._files.update(additions)

    def offers(self) -> list[dict]:
        result = []
        for source, path in self._files.items():
            path = self._resolve(path)
            size = path.stat().st_size
            result.append({"source": source, "size_bytes": size, "estimated_read_units": max(1, (size + 1023) // 1024)})
        return result

    def already_searched(self, source: str, skill: str) -> bool:
        return (source, _skill_key(skill)) in self._searched

    def searched_pairs(self) -> list[dict]:
        return [{"source": source, "skill": " / ".join(skills)} for source, skills in sorted(self._searched)]

    def snapshots_for(self, skill: str) -> dict[str, str]:
        key = _skill_key(skill)
        return {source: text for (source, target), text in self._snapshots.items() if target == key}

    def search_project_evidence(self, skill: str, source: str) -> ProjectSearchResult:
        """Search one explicitly authorized project file for literal skill aliases.

        Hits are candidates, not proof of competence. Never invent a source or path.
        """
        args = SearchProjectEvidenceArguments(skill=skill, source=source)
        if args.source not in self._files:
            raise PermissionError("Project source is not explicitly authorized")
        path = self._resolve(self._files[args.source])
        # Reject a changed symlink/file identity before any read.
        if path != self._files[args.source]:
            raise PermissionError("Authorized file identity changed")
        key = (args.source, _skill_key(args.skill))
        if key in self._searched:
            raise ValueError("Duplicate file/skill search is prohibited")
        if self.search_count >= self.max_searches:
            raise ValueError("Supplemental search limit reached")
        self._searched.add(key)
        self.search_count += 1
        if path.stat().st_size > MAX_FILE_BYTES:
            raise ValueError("Project material exceeds the 64 KiB limit")
        text = read_resume(str(path), allowed_directory=EXAMPLES_DIRECTORY)
        if len(text.encode("utf-8")) > MAX_FILE_BYTES:
            raise ValueError("Project material exceeds the 64 KiB limit")
        self._snapshots[key] = text
        name = canonical_skill(args.skill)
        aliases = project_search_keywords(args.skill)
        hit_lines = {line for hit in find_evidence(text, aliases) for line in hit.evidence}
        digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
        candidates = []
        for number, line in enumerate(text.split("\n"), 1):
            if line in hit_lines:
                # Original line and surrounding paragraph are retained verbatim.
                contexts = validate_quote(text, line, args.source)
                context = next(item.context for item in contexts if item.start_line == number)
                candidates.append(ProjectEvidenceCandidate(
                    source=args.source, line_number=number, text=line, context=context, sha256=digest,
                ))
        return ProjectSearchResult(skill=name, source=args.source, candidates=candidates)

    def registry(self) -> ToolRegistry:
        registry = ToolRegistry()
        registry.register("search_project_evidence", SearchProjectEvidenceArguments, self.search_project_evidence)
        return registry
