"""python -m evaluation.run defaults to offline scripted validation."""

import argparse
import json
import os
from pathlib import Path

from .clients import ObservedLLM, RequestBudget, ScriptedLLM, UsageSDK
from .dataset import dataset_fingerprint, load_dataset, verify_gold_freeze
from .methods import run_method
from .report import build_report, validate_report_output, write_report


def live_client(model, max_requests, global_budget):
    # Called only after explicit live-run validation. No dotenv loading.
    from openai import OpenAI
    from src.deepseek import BASE_URL, DeepSeekLLMClient
    key = os.environ.get("DEEPSEEK_API_KEY")
    if not key:
        raise ValueError("DEEPSEEK_API_KEY is missing from process environment")
    sdk = UsageSDK(OpenAI(api_key=key, base_url=BASE_URL, max_retries=0, timeout=30))
    client = DeepSeekLLMClient(model=model, sdk_client=sdk, max_calls=max_requests, max_tokens=1024)
    return ObservedLLM(client, usage_source=sdk, global_budget=global_budget)


def prepare_run(dataset, *, case_ids=None, methods=("single", "fixed", "agent"), mode="mock",
                allow_paid=False, model=None, max_requests=12, max_total_requests=25,
                normal_access_control=False):
    """Shared offline validation for --check-only and actual execution."""
    if mode not in {"mock", "real"} or not methods or len(set(methods)) != len(methods) or set(methods) - {"single", "fixed", "agent"}:
        raise ValueError("Invalid mode or methods")
    if type(max_requests) is not int or not 2 <= max_requests <= 12:
        raise ValueError("Per-method request cap must be between 2 and 12")
    if dataset.version == "gold-v1":
        verify_gold_freeze(dataset)  # Also reject an in-memory label edit before any calls.
    selected = dataset.cases if case_ids is None else [case for case in dataset.cases if case.id in case_ids]
    if not selected or (case_ids is not None and (len(set(case_ids)) != len(case_ids) or set(case_ids) != {case.id for case in selected})):
        raise ValueError("Unknown or duplicate case IDs")
    include_controls = mode == "mock" or normal_access_control
    run_cases = len(selected) + (sum(case.fault is not None for case in selected) if include_controls else 0)
    bound = run_cases * sum(1 if method == "single" else max_requests for method in methods)
    if mode == "real":
        if not allow_paid or case_ids is None or len(selected) > 2:
            raise ValueError("Real mode needs --allow-paid and one or two explicit --case selections")
        if type(max_total_requests) is not int or not bound <= max_total_requests <= 50:
            raise ValueError("Total request cap must cover the selected worst case and cannot exceed 50")
    elif allow_paid:
        raise ValueError("--allow-paid only applies to real mode")
    model = model or ("scripted-fixture-v1" if mode == "mock" else "deepseek-flash")
    if not isinstance(model, str) or not model.strip():
        raise ValueError("Model name must be nonblank")
    plan = {"mode": mode, "model": model, "dataset_version": dataset.version,
            "dataset_fingerprint": dataset_fingerprint(dataset), "case_ids": [case.id for case in selected],
            "method_order": list(methods),
            "per_method_request_caps": {method: 1 if method == "single" else max_requests for method in methods},
            "total_request_cap": max_total_requests if mode == "real" else None,
            "worst_case_request_reservation": bound, "normal_access_controls": include_controls}
    return selected, include_controls, plan


def run_suite(dataset, *, case_ids=None, methods=("single", "fixed", "agent"), mode="mock",
              allow_paid=False, model=None, max_requests=12, max_total_requests=25, client_factory=None,
              normal_access_control=False):
    selected, include_controls, plan = prepare_run(dataset, case_ids=case_ids, methods=methods, mode=mode,
        allow_paid=allow_paid, model=model, max_requests=max_requests, max_total_requests=max_total_requests,
        normal_access_control=normal_access_control)
    model = plan["model"]
    global_budget = RequestBudget(max_total_requests) if mode == "real" else None
    runs, controls = [], []
    conditions = [(case, False) for case in selected] + ([
        (case.model_copy(update={"fault": None}), True) for case in selected if case.fault] if include_controls else [])
    for case, is_control in conditions:
        for method in methods:
            if mode == "real" and dataset.version == "gold-v1":
                verify_gold_freeze(dataset)
            cap = 1 if method == "single" else max_requests
            observed = (client_factory(case, method, cap) if client_factory else
                        ObservedLLM(ScriptedLLM(case.id, normal_access_control=is_control)) if mode == "mock" else live_client(model, cap, global_budget))
            if mode == "real" and isinstance(observed.client, ScriptedLLM):
                raise ValueError("Scripted responses cannot be labeled real")
            if mode == "real":
                from src.deepseek import DeepSeekLLMClient
                if (type(observed.client) is not DeepSeekLLMClient or observed.client.model != model
                        or observed.client.max_calls != cap or observed.client.max_tokens != 1024
                        or observed.client.timeout != 30 or not isinstance(observed.usage_source, UsageSDK)):
                    raise ValueError("Real mode requires the configured DeepSeekLLMClient with SDK usage observation")
                observed.global_budget = global_budget
            try:
                run = run_method(case, method, observed, mode=mode, model=model, max_requests=max_requests)
                if is_control:
                    run.condition = "normal_access_control"
                    controls.append(run)
                else:
                    runs.append(run)
            finally:
                if mode == "real" and hasattr(observed.client, "close"):
                    observed.client.close()
            if mode == "real" and dataset.version == "gold-v1":
                verify_gold_freeze(dataset)  # Detect edits during a paid method before advancing.
    return build_report(dataset, runs, normal_access_runs=controls, request_plan=plan)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=("mock", "real"), default="mock")
    parser.add_argument("--allow-paid", action="store_true")
    parser.add_argument("--check-only", action="store_true", help="Validate frozen inputs, budgets and output paths without constructing any LLM/SDK client")
    parser.add_argument("--case", action="append", dest="case_ids")
    parser.add_argument("--method", choices=("single", "fixed", "agent"), action="append", dest="methods")
    parser.add_argument("--model")
    parser.add_argument("--max-requests", type=int, default=12)
    parser.add_argument("--max-total-requests", type=int, default=25)
    parser.add_argument("--normal-access-control", action="store_true", help="Live opt-in to additional fault-disabled paired runs; included automatically offline")
    parser.add_argument("--output", type=Path, default=Path("evaluation/reports"))
    args = vars(parser.parse_args(argv))
    output = args.pop("output")
    check_only = args.pop("check_only")
    if args["methods"] is None:
        args["methods"] = ("single", "fixed", "agent")
    try:
        dataset = load_dataset()
        _, _, plan = prepare_run(dataset, **args)
        validate_report_output(args["mode"], output)
        if check_only:
            print("CHECK ONLY: no LLM/SDK client constructed; no API request or report write.")
            print(json.dumps({**plan, "planned_reports": [str(output / f"{args['mode']}.{extension}")
                                                         for extension in ["json", "md"]]}, indent=2))
            return 0
        report = run_suite(dataset, **args)
        write_report(report, output)
    except Exception:
        parser.exit(2, "Evaluation not completed. Check frozen inputs, opt-in, case IDs, budgets, output collisions, SDK and process credentials; no raw exception logged.\n")
    print(report["interpretation"])
    for method, row in report["summary"].items():
        print(f"{method}: accuracy={row['skill_status_accuracy']:.4f}, statuses={row['status_counts']}, "
              f"useful={row['useful_retrievals']}/{row['retrieval_attempts']}, requests={row['llm_requests']}, "
              f"tokens={row['token_usage']['total_tokens'] if row['token_usage']['total_tokens'] is not None else 'unavailable'}")
    for method, row in report["normal_access"]["all_cases_with_controls"].items():
        print(f"normal-access {method}: accuracy={row['skill_status_accuracy']:.4f}, statuses={row['status_counts']}")
    print("Actual requests including controls: " + ", ".join(
        f"{method}={cost['llm_requests']}" for method, cost in report["execution_cost"].items()))
    print(f"Reports: {output / (report['mode'] + '.json')} and {output / (report['mode'] + '.md')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
