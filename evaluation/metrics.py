"""Gold comparison is observational: never repair predictions or rescore Single."""

from collections import Counter, defaultdict

from src.matching import canonical_skill

from .dataset import Citation, citation_locations, documents


def key(skill):
    return canonical_skill(skill).casefold()


def ratio(numerator, denominator):
    return numerator / denominator if denominator else None


def evaluate(case, run):
    gold = {key(item.skill): item for item in case.gold}
    predicted = defaultdict(list)
    for item in run.predictions:
        predicted[key(item.skill)].append(item)
    correct = sum(len(predicted[name]) == 1 and predicted[name][0].status == label.status
                  for name, label in gold.items())
    extras = len(set(predicted) - set(gold))
    texts = documents(case, supplements=run.method != "single")
    citation_total = citation_valid = positive_reviewed = positive_supported = semantic_reviewed = 0
    evidence_audit = []
    for prediction in run.predictions:
        label = gold.get(key(prediction.skill))
        for citation in prediction.citations:
            citation_total += 1
            locations = citation_locations(citation, texts)
            valid = bool(locations)
            citation_valid += valid
            relations = {ref.relation for ref in label.evidence if valid
                         and ref.source == citation.source and ref.quote in citation.quote
                         and any(loc.start_line <= ref.start_line <= ref.end_line <= loc.end_line for loc in locations)} if label else set()
            semantic_reviewed += bool(relations)
            if prediction.status in {"supported", "partial"} and relations:
                positive_reviewed += 1
                allowed = {"supports"} if prediction.status == "supported" else {"supports", "partial"}
                # Limits/denials can explain an outcome, but never supply the
                # positive practice component of supported/partial judgments.
                positive_supported += bool(relations.intersection(allowed)) and not relations.intersection({"contradicts", "negates"})
            evidence_audit.append({"skill": prediction.skill, "source": citation.source,
                                   "verbatim_and_location_valid": valid,
                                   "located_spans": [{"start_line": loc.start_line, "end_line": loc.end_line} for loc in locations],
                                   "semantic_relations": sorted(relations) if relations else ["unreviewed"]})

    # A successful literal hit is not automatically useful. Use manually
    # reviewed, relevant gold spans located in the actual retrieved context.
    seen = {(name, ref.source, ref.quote) for name, label in gold.items()
            for ref in label.evidence if ref.source == case.resume}
    useful = 0
    retrieval_audit = []
    for attempt in run.retrievals:
        name = key(attempt["skill"])
        label = gold.get(name)
        new = set()
        for candidate in attempt["candidates"] if attempt["success"] else []:
            ref = Citation(source=candidate["source"], quote=candidate["text"],
                           start_line=candidate["line_number"], end_line=candidate["line_number"],
                           resume_sha256=candidate["sha256"])
            contexts = [located.context for located in citation_locations(ref, texts)]
            if label:
                new.update((name, annotation.source, annotation.quote) for annotation in label.evidence
                           if annotation.source == attempt["source"] and annotation.relation != "irrelevant"
                           and any(annotation.quote in context for context in contexts))
        novel = bool(new - seen)
        seen.update(new)
        corrected = bool(label) and any(change["round"] == attempt.get("round")
            and key(change["skill"]) == name and change["before"] != change["after"] == label.status
            for change in run.changes) and bool(new)
        is_useful = attempt["success"] and (novel or corrected)
        useful += is_useful
        retrieval_audit.append({"skill": attempt["skill"], "source": attempt["source"],
                                "new_reviewed_evidence": novel, "correct_status_change": corrected,
                                "useful": bool(is_useful)})
    invalid_codes = {"invalid_action_arguments", "invalid_target", "duplicate_search", "search_limit"}
    invalid = sum(event.get("event") in {"decision", "search"} and event.get("error_code") in invalid_codes
                  for event in run.trace)
    duplicate = sum(event.get("event") == "search" and event.get("error_code") == "duplicate_search" for event in run.trace)
    return {"skill_correct": correct, "skill_total": len(gold) + extras,
            "unexpected_skills": extras, "duplicate_skill_predictions": sum(len(items) > 1 for items in predicted.values()),
            "skill_status_accuracy": ratio(correct, len(gold) + extras),
            "citation_valid": citation_valid, "citation_total": citation_total,
            "evidence_validity": ratio(citation_valid, citation_total),
            "semantic_reviewed": semantic_reviewed,
            "semantic_review_coverage": ratio(semantic_reviewed, citation_valid),
            "positive_citations_reviewed": positive_reviewed, "positive_citations_supported": positive_supported,
            "semantic_positive_support": ratio(positive_supported, positive_reviewed),
            "useful_retrievals": useful, "retrieval_attempts": len(run.retrievals),
            "useful_retrieval_rate": ratio(useful, len(run.retrievals)),
            "invalid_actions": invalid, "duplicate_actions": duplicate,
            "evidence_audit": evidence_audit, "retrieval_audit": retrieval_audit}


def aggregate(rows):
    if not rows:
        raise ValueError("Cannot aggregate an empty group")
    if len({(run.mode, run.model, run.method) for run, _ in rows}) != 1:
        raise ValueError("Never mix methods, mock/real modes or model identities")
    counts = Counter(run.status for run, _ in rows)
    sums = {name: sum(metrics[name] for _, metrics in rows) for name in [
        "skill_correct", "skill_total", "citation_valid", "citation_total", "semantic_reviewed",
        "positive_citations_reviewed", "positive_citations_supported", "useful_retrievals", "retrieval_attempts",
        "invalid_actions", "duplicate_actions", "unexpected_skills", "duplicate_skill_predictions"]}
    return {**sums, "runs": len(rows), "status_counts": dict(sorted(counts.items())),
            "task_completion_rate": counts["finished"] / len(rows),
            "waiting_rate": counts["waiting_for_user"] / len(rows),
            "error_rate": sum(value for status, value in counts.items() if status not in {"finished", "waiting_for_user"}) / len(rows),
            "skill_status_accuracy": ratio(sums["skill_correct"], sums["skill_total"]),
            "evidence_validity": ratio(sums["citation_valid"], sums["citation_total"]),
            "semantic_review_coverage": ratio(sums["semantic_reviewed"], sums["citation_valid"]),
            "semantic_positive_support": ratio(sums["positive_citations_supported"], sums["positive_citations_reviewed"]),
            "useful_retrieval_rate": ratio(sums["useful_retrievals"], sums["retrieval_attempts"]),
            "llm_requests": sum(run.cost["llm_requests"] for run, _ in rows),
            "api_requests": sum(run.cost["api_requests"] for run, _ in rows) if all(run.cost["api_requests"] is not None for run, _ in rows) else None,
            "token_usage": {name: sum(run.cost["token_usage"][name] for run, _ in rows)
                            if all(run.cost["token_usage"][name] is not None for run, _ in rows) else None
                            for name in ["prompt_tokens", "completion_tokens", "total_tokens"]},
            "latency_seconds": sum(run.latency_seconds for run, _ in rows)}
