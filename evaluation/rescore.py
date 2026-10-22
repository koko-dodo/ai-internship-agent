"""Offline-only re-scoring of immutable saved runs; no client construction."""

import argparse
import hashlib
import json
from pathlib import Path

from .alignment import RULES_VERSION, evaluate_aligned
from .dataset import dataset_fingerprint, load_dataset
from .methods import Run
from .metrics import aggregate
from .report import dumps


def rescore_report(source, dataset):
    if (source["dataset_version"], source["dataset_fingerprint"]) != (dataset.version, dataset_fingerprint(dataset)):
        raise ValueError("Saved report does not match the frozen dataset")
    cases = {case.id: case for case in dataset.cases}

    def rows(items):
        result = []
        for item in items:
            run = Run.model_validate(item["run"])
            if (run.mode, run.model) != (source["mode"], source["model"]):
                raise ValueError("Mixed source modes/models")
            # Keep the exact saved dictionary, not a reserialized/modified Run.
            result.append({"run": item["run"], "original_metrics": item["metrics"],
                           "metrics": evaluate_aligned(cases[run.case_id], run)})
        return result

    def summarize(items):
        return {method: aggregate([(Run.model_validate(row["run"]), row["metrics"])
                                  for row in items if row["run"]["method"] == method])
                for method in sorted({row["run"]["method"] for row in items})}

    primary = rows(source["runs"])
    controls = rows(source.get("normal_access", {}).get("controls", []))
    return {"schema_version": 1, "rules_version": RULES_VERSION,
            "report_kind": "offline_re_scored_saved_runs_not_new_model_execution",
            "scope": "Only skill-status alignment/composition changes; evidence/retrieval metrics retain legacy rules. Model scores, outputs, verified flags, usage and latency are original observations.",
            "dataset_version": dataset.version, "dataset_fingerprint": source["dataset_fingerprint"],
            "mode": source["mode"], "model": source["model"],
            "interpretation": source["interpretation"],
            "source_semantic_fingerprint": source["semantic_fingerprint"],
            "original_summary": source["summary"], "summary": summarize(primary),
            "by_scenario": {scenario: summarize([row for row in primary if row["run"]["scenario"] == scenario])
                            for scenario in sorted({row["run"]["scenario"] for row in primary})},
            "runs": primary,
            "normal_access_controls": {"runs": controls, "summary": summarize(controls)},
            "source_metadata": {name: source.get(name) for name in ["request_plan", "execution_order", "generation_settings", "execution_cost", "policy_ablation", "mock_script_fingerprint"]}}


def markdown(report):
    lines = [f"# Saved-run re-score — {report['rules_version']}", "",
             f"Mode: `{report['mode']}`; model: `{report['model']}`; Gold: `{report['dataset_version']}`.", "",
             report["interpretation"], "", report["scope"], "",
             f"Source SHA-256: `{report['source_sha256']}`", "",
             "No API calls or new model judgments. This is a post-hoc protocol revision, not an independent replication.", "",
             "| Case | Method | Original correct / total | Aligned correct / total | Original / aligned accuracy |",
             "| --- | --- | --- | --- | --- |"]
    for row in report["runs"]:
        old, new, run = row["original_metrics"], row["metrics"], row["run"]
        lines.append(f"| {run['case_id']} | {run['method']} | {old['skill_correct']}/{old['skill_total']} | "
                     f"{new['skill_correct']}/{new['skill_total']} | {old['skill_status_accuracy']} / {new['skill_status_accuracy']} |")
    lines += ["", "## Alignment trace", ""]
    for row in report["runs"]:
        lines += [f"### Case {row['run']['case_id']} / {row['run']['method']}", ""]
        # JSON fencing preserves arbitrary original model names without treating
        # their pipe/newline characters as Markdown table structure.
        lines += ["```json", dumps(row["metrics"]["alignment"]).rstrip(), "```", ""]
    lines += ["Condition-only claims cannot replace a missing base skill. Unknown names still add denominator penalties. "
              "Identical or conflicting duplicate base claims are not silently merged. "
              "Condition states are retained; conservative composition never upgrades the base status. "
              "Evidence/Useful Retrieval metrics have NOT been normalized by this revision. "
              "Fault-disabled controls, if present, stay separate in JSON. "
              "Original policy-ablation metadata is historical, including its old accuracies, and is not a new policy experiment.", ""]
    return "\n".join(lines)


def write_rescore(source_path, output):
    if source_path.is_symlink() or source_path.suffix != ".json":
        raise ValueError("Source must be a regular saved JSON report")
    # A fresh directory and exclusive writes protect all previous artifacts.
    if output.exists() or output.is_symlink() or any(parent.is_symlink() for parent in output.parents):
        raise ValueError("Choose a fresh output directory without symlink parents")
    raw = source_path.read_bytes()
    report = rescore_report(json.loads(raw), load_dataset())
    report["source_sha256"] = hashlib.sha256(raw).hexdigest()
    output.mkdir(parents=True, exist_ok=False)
    for extension, content in [("json", dumps(report)), ("md", markdown(report))]:
        with (output / f"re-scored.{extension}").open("x", encoding="utf-8") as handle:
            handle.write(content)
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    report = write_rescore(args.source, args.output)
    for method, metrics in report["summary"].items():
        print(f"{method}: {metrics['skill_correct']}/{metrics['skill_total']} accuracy={metrics['skill_status_accuracy']}")


if __name__ == "__main__":
    main()
