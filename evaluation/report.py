"""Stable serialization, semantic fingerprints, and transparent grouped reports."""

import hashlib
import json
from pathlib import Path

from .dataset import dataset_fingerprint
from .metrics import aggregate, evaluate


def dumps(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, indent=2, allow_nan=False) + "\n"


def build_report(dataset, runs, *, normal_access_runs=(), request_plan=None):
    all_runs = [*runs, *normal_access_runs]
    identities = {(run.mode, run.model) for run in all_runs}
    if len(identities) != 1:
        raise ValueError("Mock and real results or different models require separate reports")
    if any(run.mode == "mock" and (run.cost["api_requests"] is not None or
           any(value is not None for value in run.cost["token_usage"].values())) for run in all_runs):
        raise ValueError("Mock runs cannot claim actual API requests or tokens")
    case_map = {case.id: case for case in dataset.cases}
    if len({(run.case_id, run.method) for run in runs}) != len(runs):
        raise ValueError("Duplicate run; do not silently change weighting")
    primary = {(run.case_id, run.method): run for run in runs}
    control_keys = {(run.case_id, run.method) for run in normal_access_runs}
    if len(control_keys) != len(normal_access_runs):
        raise ValueError("Duplicate normal-access control")
    for control in normal_access_runs:
        configured = primary.get((control.case_id, control.method))
        if (configured is None or case_map[control.case_id].fault is None or control.injected_fault is not None
                or control.condition != "normal_access_control"
                or (control.input_fingerprint, control.authorized_sources, control.budgets) !=
                   (configured.input_fingerprint, configured.authorized_sources, configured.budgets)):
            raise ValueError("Control must be a paired rerun differing only in injected fault condition")
    rows = [(run, evaluate(case_map[run.case_id], run)) for run in runs]
    control_rows = [(run, evaluate(case_map[run.case_id], run)) for run in normal_access_runs]
    methods = sorted({run.method for run in runs})
    def summaries(group):
        return {method: aggregate([(run, metrics) for run, metrics in group if run.method == method])
                for method in methods if any(run.method == method for run, _ in group)}
    summary = {method: aggregate([(run, metrics) for run, metrics in rows if run.method == method]) for method in methods}
    non_fault_rows = [(run, metrics) for run, metrics in rows if case_map[run.case_id].fault is None]
    required_controls = {identity for identity in primary if case_map[identity[0]].fault is not None}
    complete = required_controls.issubset(control_keys)
    execution_stats = summaries([*rows, *control_rows])
    scenarios = {scenario: {method: aggregate([(run, metrics) for run, metrics in rows
                  if run.scenario == scenario and run.method == method]) for method in methods
                  if any(run.scenario == scenario and run.method == method for run in runs)}
                  for scenario in sorted({run.scenario for run in runs})}
    paired = []
    metrics_by_run = {(run.case_id, run.method): metrics for run, metrics in rows}
    for case_id in sorted({run.case_id for run in runs}):
        pair = {run.method: run for run in runs if run.case_id == case_id}
        if "fixed" not in pair or "agent" not in pair:
            continue
        fixed, agent = pair["fixed"], pair["agent"]
        comparable = (fixed.input_fingerprint == agent.input_fingerprint
                      and fixed.authorized_sources == agent.authorized_sources and fixed.budgets == agent.budgets)
        paired.append({"case_id": case_id, "same_inputs_grants_budgets": comparable,
                       "same_initial_states": fixed.initial_states == agent.initial_states,
                       "same_initial_checkpoint": fixed.initial_checkpoint_fingerprint == agent.initial_checkpoint_fingerprint,
                       "fixed_accuracy": metrics_by_run[(case_id, "fixed")]["skill_status_accuracy"],
                       "agent_accuracy": metrics_by_run[(case_id, "agent")]["skill_status_accuracy"],
                       "fixed_status": fixed.status, "agent_status": agent.status,
                       "fixed_requests": fixed.cost["llm_requests"], "agent_requests": agent.cost["llm_requests"],
                       "fixed_retrievals": len(fixed.retrievals), "agent_retrievals": len(agent.retrievals)})
    mode, model = next(iter(identities))
    report = {"schema_version": 2, "dataset_version": dataset.version,
              "dataset_fingerprint": dataset_fingerprint(dataset), "mode": mode, "model": model,
              "annotation_provenance": dataset.provenance,
              "request_plan": request_plan,
              "interpretation": "SCRIPTED FRAMEWORK VALIDATION ONLY; not real model accuracy" if mode == "mock"
              else "Small live-model experiment; review provenance is recorded, no multiple-annotator agreement claimed",
              "summary": summary, "by_scenario": scenarios, "policy_ablation": paired,
              "execution_order": [{"case_id": run.case_id, "method": run.method, "condition": run.condition}
                                  for run in all_runs],
              "normal_access": {"non_fault_subset": summaries(non_fault_rows),
                  "mock_control_script": "Original script plus explicit control-only FINISH; original fault scripts stop at SEARCH" if mode == "mock" else None,
                  "fault_case_ids": sorted({run.case_id for run in runs if case_map[run.case_id].fault is not None}),
                  "controls_complete": complete,
                  "missing_control_pairs": [list(identity) for identity in sorted(required_controls - control_keys)],
                  "control_summary": summaries(control_rows),
                  "all_cases_with_controls": summaries([*non_fault_rows, *control_rows]) if complete else {},
                  "controls": [{"run": run.model_dump(), "metrics": metrics} for run, metrics in control_rows]},
              "execution_cost": {method: {name: stats[name] for name in
                  ["llm_requests", "api_requests", "token_usage", "latency_seconds"]}
                  for method, stats in execution_stats.items()},
              "runs": [{"run": run.model_dump(), "metrics": metrics} for run, metrics in rows]}
    report["mock_script_fingerprint"] = hashlib.sha256(Path(__file__).with_name("mock_scripts.json").read_bytes()).hexdigest() if mode == "mock" else None
    report["generation_settings"] = None if mode == "mock" else {
        "max_tokens": 1024, "timeout_seconds": 30, "sdk_retries": 0,
        "sampling": "provider defaults, independently sampled; no seed"}
    # Same semantic result has the same hash. Actual latency is intentionally
    # volatile, measured rather than fabricated to achieve byte equality.
    stable = json.loads(dumps(report))
    def strip_latency(value):
        if isinstance(value, dict):
            value.pop("latency_seconds", None)
            for item in value.values():
                strip_latency(item)
        elif isinstance(value, list):
            for item in value:
                strip_latency(item)
    strip_latency(stable)
    report["semantic_fingerprint"] = hashlib.sha256(dumps(stable).encode()).hexdigest()
    return report


def percent(value):
    return f"{100 * value:.1f}%" if value is not None else "unavailable"


def markdown(report):
    lines = [f"# Day 6 evaluation — {report['mode']}", "", report["interpretation"], "",
             f"Model: `{report['model']}`; dataset: `{report['dataset_version']}`.", "",
             report["annotation_provenance"], "",
             f"Dataset fingerprint: `{report['dataset_fingerprint']}`", "",
             f"Semantic fingerprint (excluding measured latency): `{report['semantic_fingerprint']}`", "",
             "Single sees only resume/JD and keeps raw, unverified judgments and model scores. "
             "Fixed and Agent share grants, semantic prompts, evidence validation, scoring and caps; "
             "only action selection changes. Fixed decisions do not count as LLM requests.", "",
             "JSON model_outputs retains original normalized-client response text by stage for every method. "
             "initial_states and predictions are separate validated results for Fixed/Agent; Single remains unverified. "
             "No prompts, HTTP headers or raw SDK errors are recorded. execution_order gives actual method order.", "",
             "| Method | Skill accuracy | Verbatim validity | Positive semantic support | Finished | Waiting | Error |",
             "| --- | --- | --- | --- | --- | --- | --- |"]
    for method, row in report["summary"].items():
        lines.append(f"| {method} | " + " | ".join(percent(row[name]) for name in [
            "skill_status_accuracy", "evidence_validity", "semantic_positive_support", "task_completion_rate", "waiting_rate", "error_rate"]) + " |")
    lines += ["", "Semantic support uses reviewed gold excerpts only; unknown wording remains unreviewed. "
              "Verbatim validity does not prove relevance or ownership. No citations means unavailable, not 100%.", "",
              "| Method | Useful / attempts | LLM requests | API attempts | Tokens | Seconds | Invalid / duplicate |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for method, row in report["summary"].items():
        tokens = row["token_usage"]["total_tokens"]
        api = row["api_requests"]
        lines.append(f"| {method} | {row['useful_retrievals']} / {row['retrieval_attempts']} | {row['llm_requests']} | "
                     f"{api if api is not None else 'unavailable'} | {tokens if tokens is not None else 'unavailable'} | "
                     f"{row['latency_seconds']:.6f} | {row['invalid_actions']} / {row['duplicate_actions']} |")
    normal = report["normal_access"]
    lines += ["", "## Runtime faults versus normal access", "",
              "Overall above retains configured faults. The non-fault subset excludes fault cases for all methods; "
              "it is not a counterfactual rerun. Controls below are actual paired runs with only the injected fault "
              "disabled. Gold, files, grants, policies and caps stay the same. Live LLM sampling can still differ.", "",
              "| Condition | Method | Runs | Skill accuracy | Finished / waiting / errors | Requests |",
              "| --- | --- | --- | --- | --- | --- |"]
    for condition, stats in [("non-fault subset", normal["non_fault_subset"]),
                             ("fault-disabled controls", normal["control_summary"]),
                             ("all cases, fault-disabled replacements", normal["all_cases_with_controls"])]:
        for method, row in stats.items():
            finished = row["status_counts"].get("finished", 0)
            waiting = row["status_counts"].get("waiting_for_user", 0)
            lines.append(f"| {condition} | {method} | {row['runs']} | {percent(row['skill_status_accuracy'])} | "
                         f"{finished} / {waiting} / {row['runs'] - finished - waiting} | {row['llm_requests']} |")
    if not normal["controls_complete"]:
        lines += ["", "Fault-disabled controls were not completed for all pairs; no all-cases normal-access result is claimed."]
    lines += ["", "Actual execution requests including controls: " + ", ".join(
        f"{method}={cost['llm_requests']}" for method, cost in report["execution_cost"].items()) + "."]
    lines += ["", "## Scenario groups", "",
              "| Scenario | Method | Skill accuracy | Finished / waiting / errors | Useful / attempts | Requests |",
              "| --- | --- | --- | --- | --- | --- |"]
    for scenario, methods in report["by_scenario"].items():
        for method, row in methods.items():
            counts = row["status_counts"]
            waiting = counts.get("waiting_for_user", 0)
            finished = counts.get("finished", 0)
            lines.append(f"| {scenario} | {method} | {percent(row['skill_status_accuracy'])} | "
                         f"{finished} / {waiting} / {row['runs'] - finished - waiting} | "
                         f"{row['useful_retrievals']} / {row['retrieval_attempts']} | {row['llm_requests']} |")
    lines += ["", "## Policy ablation and limitations", "",
              "| Case | Same inputs / grants / caps | Same initial checkpoint | Fixed / Agent accuracy | Fixed / Agent retrievals | Fixed / Agent requests |",
              "| --- | --- | --- | --- | --- | --- |"]
    for pair in report["policy_ablation"]:
        lines.append(f"| {pair['case_id']} | {pair['same_inputs_grants_budgets']} | {pair['same_initial_checkpoint']} | "
                     f"{percent(pair['fixed_accuracy'])} / {percent(pair['agent_accuracy'])} | "
                     f"{pair['fixed_retrievals']} / {pair['agent_retrievals']} | {pair['fixed_requests']} / {pair['agent_requests']} |")
    lines += ["",
              "This is a capability-controlled policy comparison: identical production executor, judge prompts, "
              "scorer and authorized inputs. JSON includes per-case comparability and initial-state checks. "
              "Live calls are independently sampled; different initial judgments/reviews are confounders, "
              "so do not interpret a difference as a causal autonomy benefit. Actual file counts are reported.", "",
              "Mock answers/actions are predefined, including deliberate errors. They establish no superiority "
              "of Agent or Workflow. A finished run may be factually wrong; waiting is separate from failure. "
              "Small reviewed fixtures, partial semantic annotation and no multiple-annotator agreement limit generalization.", "",
              "Request counts include failed LLM attempts; API attempts and usage are provider-observed only. "
              "Tokens are unavailable if any call lacks usage; none are estimated. Latency is measured locally, "
              "and mock timing says nothing about live API performance. JSON retains raw Single output, "
              "predictions, traces, interactions, budgets and evidence/retrieval audits.", ""]
    return "\n".join(lines)


def validate_report_output(mode, output_directory):
    if mode not in {"mock", "real"}:
        raise ValueError("Invalid report mode")
    if output_directory.is_symlink() or (output_directory.exists() and not output_directory.is_dir()):
        raise ValueError("Report output must be a directory, not a symlink or file")
    for extension in ["json", "md"]:
        target = output_directory / f"{mode}.{extension}"
        if target.is_symlink() or (target.exists() and (mode == "real" or not target.is_file())):
            raise ValueError("Refusing report collision or symlink; choose a fresh output directory")


def write_report(report, output_directory):
    validate_report_output(report["mode"], output_directory)
    output_directory.mkdir(parents=True, exist_ok=True)
    for extension, content in [("json", dumps(report)), ("md", markdown(report))]:
        target = output_directory / f"{report['mode']}.{extension}"
        # Exclusive create also prevents a collision introduced after preflight.
        with target.open("x" if report["mode"] == "real" else "w", encoding="utf-8") as handle:
            handle.write(content)
