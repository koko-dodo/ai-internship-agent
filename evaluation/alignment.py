"""Opt-in, finite evaluation vocabulary. Never change production predictions.

No fuzzy matching, substring matching, Gold-status lookup, or LLM calls.
Unsupported JD grammar/condition names deliberately remain unexpected skills.
"""

import re
from collections import defaultdict

from src.matching import canonical_skill

from .dataset import read_source
from .metrics import evaluate, ratio


RULES_VERSION = "skill-alignment-v2"


def text_key(value):
    return " ".join(value.split()).casefold()


# Complete-name equivalence only. Products, subskills and operating conditions
# are not aliases (notably MySQL, NoSQL, retrieval-only, production experience).
ALIASES = {
    "sql querying": "SQL", "sql queries": "SQL", "sql查询": "SQL",
    "sql 查询": "SQL", "sql query writing": "SQL",
    "retrieval augmented generation": "RAG", "retrieval-augmented generation": "RAG",
}


def skill_name(value):
    return ALIASES.get(text_key(value), canonical_skill(value))


def skill_key(value):
    return text_key(skill_name(value))


# Explicit condition ontology. A compound phrase retains BOTH obligations.
CONDITIONS = {
    "real business data in production": ("real_business_data", "production"),
    "production experience": ("production",),
    "production environment experience": ("production",),
    "real business data experience": ("real_business_data",),
}


def condition_ids(value):
    value = text_key(value)
    if value.startswith("experience with "):
        value = value.removeprefix("experience with ")
    return CONDITIONS.get(value)


def jd_bindings(case):
    """Only explicit full-sentence skill/condition bindings in the JD count.

    Do not infer attachment from file names, nearby keywords, or Gold status.
    The grammar works for any Gold skill, but is intentionally small.
    """
    gold = {skill_key(label.skill) for label in case.gold}
    bindings = defaultdict(set)
    for sentence in re.split(r"[.!?\n]", read_source(case.jd)):
        match = re.fullmatch(r"\s*(.+?) must include experience with (.+?)\s*", sentence, re.I)
        if match:
            owner = skill_key(match[1])
            conditions = condition_ids(match[2])
            if owner in gold and conditions:
                bindings[owner].update(conditions)
    return dict(bindings)


def map_prediction(value, gold_names, bindings):
    """Return skill identity OR an explicitly bound condition, never both."""
    canonical = skill_name(value)
    key = skill_key(value)
    # A Gold skill literally bearing this name takes precedence over parsing.
    if key in gold_names:
        return {"kind": "skill", "normalized_skill": gold_names[key], "key": key,
                "conditions": [], "reason": "exact_name" if text_key(value) == key else "declared_full_name_alias"}
    conditions = condition_ids(value)
    owner = None
    if conditions:
        owners = [name for name, slots in bindings.items() if set(conditions) <= slots]
        if len(owners) == 1:
            owner = owners[0]
    else:
        # Entire qualified names only, using recognized condition vocabulary.
        # SQL production experience is a condition of SQL, NOT a SQL alias.
        for phrase, slots in CONDITIONS.items():
            for separator in (" on ", " "):
                suffix = separator + phrase
                if text_key(value).endswith(suffix):
                    base = text_key(value)[:-len(suffix)]
                    base_key = skill_key(base)
                    if base_key in bindings and set(slots) <= bindings[base_key]:
                        owner, conditions = base_key, slots
                        break
            if owner:
                break
    if owner:
        return {"kind": "condition", "normalized_skill": gold_names[owner], "key": owner,
                "conditions": list(conditions), "reason": "declared_condition_and_explicit_JD_binding"}
    return {"kind": "unexpected", "normalized_skill": canonical, "key": key,
            "conditions": [], "reason": "no_unambiguous_declared_skill_or_JD_condition_binding"}


def combined_status(primary, conditions, required):
    """Conservative assembly, not a new semantic judgment or numeric score.

    The base status is never upgraded. Conflicting/uncertain condition claims
    yield uncertain; explicit unmet conditions cap supported at partial.
    A split supported claim with missing condition coverage is uncertain.
    """
    if primary in {"not_found", "uncertain"} or not conditions:
        return primary
    slots = defaultdict(set)
    for mapping in conditions:
        for slot in mapping["conditions"]:
            slots[slot].add(mapping["status"])
    if any(len(states) != 1 or "uncertain" in states for states in slots.values()):
        return "uncertain"
    if primary == "partial":
        return "partial"
    if any(states != {"supported"} for states in slots.values()):
        return "partial"
    return "supported" if required <= slots.keys() else "uncertain"


def evaluate_aligned(case, run):
    """Versioned skill-status metric; all other legacy metrics stay unchanged.

    Audit every input by index, retaining its original name/status/citations in
    the Run. Conditions cannot supply a missing base skill. Duplicate base
    claims remain incorrect, including identical aliases and conflicting ones.
    """
    legacy = evaluate(case, run)
    names = {skill_key(label.skill): skill_name(label.skill) for label in case.gold}
    if len(names) != len(case.gold):
        raise ValueError("Gold skill collision under alignment rules")
    bindings = jd_bindings(case)
    mappings = []
    primary, conditions, extras = defaultdict(list), defaultdict(list), defaultdict(list)
    for index, prediction in enumerate(run.predictions):
        mapped = {"index": index, "original_skill": prediction.skill, "status": prediction.status,
                  **map_prediction(prediction.skill, names, bindings)}
        mappings.append(mapped)
        if mapped["kind"] == "skill":
            primary[mapped["key"]].append(mapped)
        elif mapped["kind"] == "condition":
            conditions[mapped["key"]].append(mapped)
        else:
            extras[mapped["key"]].append(mapped)
    judgments = []
    correct = 0
    for label in case.gold:
        key = skill_key(label.skill)
        base = primary[key]
        status = combined_status(base[0]["status"], conditions[key], bindings.get(key, set())) if len(base) == 1 else None
        correct += status == label.status
        judgments.append({"skill": names[key], "status": status,
                          "primary_indices": [item["index"] for item in base],
                          "condition_indices": [item["index"] for item in conditions[key]],
                          "required_conditions": sorted(bindings.get(key, set())),
                          "reason": "missing_primary" if not base else "duplicate_primary" if len(base) > 1 else "conservative_condition_composition"})
    total = len(names) + len(extras)
    return {**legacy, "rules_version": RULES_VERSION,
            "normalization_scope": "skill_metrics_only; evidence_and_retrieval_metrics_remain_legacy",
            "skill_correct": correct, "skill_total": total,
            "unexpected_skills": len(extras),
            "duplicate_skill_predictions": sum(len(items) > 1 for items in [*primary.values(), *extras.values()]),
            "skill_status_accuracy": ratio(correct, total),
            "alignment": {"mappings": mappings, "judgments": judgments,
                          "unexpected_keys": sorted(extras)}}
