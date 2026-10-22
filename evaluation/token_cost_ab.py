"""Offline format-only A/B: scripted cases and saved-response replay, no SDK.

Replaying saved model answers tests transport/control equivalence, not how a
live model would react to a different prompt. Never reuse saved token usage.
"""

import argparse
import hashlib
import json
from pathlib import Path
from unittest.mock import patch

from src.autonomy import EvidenceGatheringSession
from src.llm import LLMResponse, MockLLMClient

from .clients import ObservedLLM, ScriptedLLM
from .dataset import dataset_fingerprint, load_dataset
from .methods import run_method
from .report import dumps


ROOT = Path(__file__).resolve().parent.parent


class OriginalFormattingSession(EvidenceGatheringSession):
    """The exact pre-optimization encoder; no copied controller logic."""

    @staticmethod
    def _encode_request(schema, data, model):
        return json.dumps({"schema": schema, "data": data}, ensure_ascii=False)


class CapturingClient:
    """Prompt inspection in memory only; artifacts contain lengths, not text."""

    def __init__(self, client):
        self.client, self.prompts = client, []

    def complete(self, messages, tools):
        self.prompts.append(([message.content for message in messages], list(tools)))
        return self.client.complete(messages, tools)


def once(case, *, original, saved=None):
    client = ScriptedLLM(case.id) if saved is None else MockLLMClient([
        LLMResponse.model_validate(output["response"]) for output in saved["model_outputs"]])
    capture = CapturingClient(client)
    observed = ObservedLLM(capture)
    controller = OriginalFormattingSession if original else EvidenceGatheringSession
    with patch("evaluation.methods.EvidenceGatheringSession", controller):
        run = run_method(case, "agent", observed, model="offline-format-ab")
    return run, capture.prompts


def is_decision(contents):
    return "action" in json.loads(contents[-1].rsplit("\n", 1)[-1])["schema"]["properties"]


def compare(case, *, saved=None):
    before, old_prompts = once(case, original=True, saved=saved)
    after, new_prompts = once(case, original=False, saved=saved)
    same_data = len(old_prompts) == len(new_prompts)
    same_other_prompts = same_data
    for (old, old_tools), (new, new_tools) in zip(old_prompts, new_prompts):
        same_data &= old_tools == new_tools and len(old) == len(new)
        for old_content, new_content in zip(old, new):
            old_prefix, old_json = old_content.rsplit("\n", 1)
            new_prefix, new_json = new_content.rsplit("\n", 1)
            same_data &= old_prefix == new_prefix and json.loads(old_json) == json.loads(new_json)
        if not is_decision(old):
            same_other_prompts &= old == new

    def counts(run, prompts):
        sizes = [sum(len(content or "") for content in contents)
                 for contents, _ in prompts if is_decision(contents)]
        return {"llm_requests": run.cost["llm_requests"], "decision_calls": len(sizes),
                "decision_context_characters": sum(sizes), "decision_context_characters_per_call": sizes,
                "retrieval_attempts": len(run.retrievals), "status": run.status,
                "waiting_events": sum(event.get("status") == "waiting_for_user" for event in run.trace),
                "error_codes": [event["error_code"] for event in run.trace if event.get("error_code")],
                "token_usage": "unavailable"}

    return {"case_id": case.id, "scenario": case.scenario,
            "fixture": "saved_response_replay" if saved else "scripted_mock",
            "before": counts(before, old_prompts), "after": counts(after, new_prompts),
            "checks": {
                "all_request_structures_values_instructions_equal": bool(same_data),
                "non_decision_prompts_byte_equal": bool(same_other_prompts),
                "run_equal_except_measured_latency": before.model_dump(exclude={"latency_seconds"}) == after.model_dump(exclude={"latency_seconds"}),
                "predictions_and_citations_equal": before.predictions == after.predictions,
                "scores_equal": before.score == after.score,
                "trace_and_interactions_equal": before.trace == after.trace and before.interactions == after.interactions}}


def build_ab():
    dataset = load_dataset()
    cases = {case.id: case for case in dataset.cases}
    rows = [compare(case) for case in dataset.cases]
    sources = {}
    # These are fixture inputs, not case-specific production optimization rules.
    for case_id in ["02", "05"]:
        path = ROOT / f"evaluation/reports/deepseek-case{case_id}-run01/real.json"
        raw = path.read_bytes()
        source = json.loads(raw)
        if source["dataset_fingerprint"] != dataset_fingerprint(dataset):
            raise ValueError("Saved source and frozen dataset differ")
        saved = next(row["run"] for row in source["runs"] if row["run"]["method"] == "agent")
        rows.append(compare(cases[case_id], saved=saved))
        sources[str(path.relative_to(ROOT))] = hashlib.sha256(raw).hexdigest()
    return {"mode": "offline_mock_and_saved_response_replay", "optimization": "compact_action_decision_JSON_only",
            "interpretation": "Fixed responses with current code/frozen fixtures validate format and controller equivalence, not live model behavior, historical HTTP prompt lengths or token savings.",
            "character_definition": "Python len() of message.content summed over all action-decision requests; includes instruction, schema and data; not tokens or bytes.",
            "dataset_version": dataset.version, "dataset_fingerprint": dataset_fingerprint(dataset),
            "source_sha256": sources, "token_usage": "unavailable", "rows": rows}


def markdown(report):
    lines = ["# Token cost optimization — offline A/B", "", report["interpretation"], "",
             report["character_definition"], "", "Only JSON formatting whitespace outside string values changes.", "",
             "| Fixture | Case | Decision calls before → after | Decision context characters before → after | All LLM requests | Retrieval attempts | Final status |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for row in report["rows"]:
        a, b = row["before"], row["after"]
        lines.append(f"| {row['fixture']} | {row['case_id']} | {a['decision_calls']} → {b['decision_calls']} | "
                     f"{a['decision_context_characters']} → {b['decision_context_characters']} | "
                     f"{a['llm_requests']} → {b['llm_requests']} | {a['retrieval_attempts']} → {b['retrieval_attempts']} | {b['status']} |")
    lines += ["", "All equivalence checks passed: " + str(all(all(row["checks"].values()) for row in report["rows"])), "",
              "JSON retains per-call character counts, waiting/error counts, equivalence checks and source hashes. "
              "No historical API usage is attributed to the replay. Real token usage is unavailable; no token savings rate is estimated.", ""]
    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists() or args.output.is_symlink() or any(p.is_symlink() for p in args.output.parents):
        raise ValueError("Choose a fresh output directory without symlink parents")
    report = build_ab()
    if not all(all(row["checks"].values()) for row in report["rows"]):
        raise ValueError("A/B behavior or request data changed")
    args.output.mkdir(parents=True, exist_ok=False)
    for suffix, content in [("json", dumps(report)), ("md", markdown(report))]:
        with (args.output / f"offline-ab.{suffix}").open("x", encoding="utf-8") as handle:
            handle.write(content)
    print(markdown(report))


if __name__ == "__main__":
    main()
