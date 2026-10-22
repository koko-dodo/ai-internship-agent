"""Scripted fixtures and request/usage observation; no SDK import on offline paths."""

import json
from pathlib import Path
from types import SimpleNamespace

from src.autonomy import LLMBudgetExceeded
from src.llm import LLMResponse


class ScriptedLLM:
    """Separate scripts, never gold access. Wrong answers are intentional."""

    def __init__(self, case_id, *, normal_access_control=False):
        self.script = json.loads(Path(__file__).with_name("mock_scripts.json").read_text())[case_id]
        if normal_access_control:
            # Original fault scripts stop at SEARCH because the tool aborts.
            # The explicitly new control condition needs its own final reply;
            # never silently repair exhaustion in the configured runs.
            self.script["actions"].append({"action": "FINISH", "reason": "Preset control-only end after the fault-disabled sequence; not model reasoning."})
        self.action_index = 0

    def complete(self, messages, tools):
        request = json.loads(messages[-1].content.split("\n")[-1])
        properties = request["schema"]["properties"]
        if "action" in properties:
            payload = self.script["actions"][self.action_index]
            self.action_index += 1
        elif "required_skills" in properties:
            payload = self.script["job"]
        elif "citations" in properties:
            payload = self.script["supplemental"][request["data"]["skill"]]
        else:
            payload = dict(self.script["initial"])
            if "model_score" in properties:
                payload["model_score"] = self.script["model_score"]
        return LLMResponse(final_answer=json.dumps(payload, ensure_ascii=False))


class RequestBudget:
    def __init__(self, limit):
        self.limit, self.used = limit, 0

    def take(self):
        if self.used >= self.limit:
            raise LLMBudgetExceeded("Evaluation request budget exhausted")
        self.used += 1


class ObservedLLM:
    """Counts real LLM calls only; deterministic workflow decisions bypass it."""

    def __init__(self, client, *, usage_source=None, global_budget=None):
        self.client, self.usage_source, self.global_budget = client, usage_source, global_budget
        self.requests = 0
        self.usages = []
        # Report artifact only, separate from sanitized execution traces. Keep
        # original response text, never prompts, credentials or SDK exceptions.
        self.outputs = []

    @staticmethod
    def stage(messages):
        try:
            properties = json.loads(messages[-1].content.split("\n")[-1])["schema"]["properties"]
            if "model_score" in properties:
                return "single_assessment"
            if "action" in properties:
                return "action_decision"
            if "required_skills" in properties:
                return "jd_extraction"
            if "citations" in properties:
                return "supplemental_assessment"
            if "assessments" in properties:
                return "initial_assessment"
        except (AttributeError, IndexError, KeyError, TypeError, ValueError):
            pass
        return "unclassified"

    def complete(self, messages, tools):
        if self.global_budget:
            self.global_budget.take()
        self.requests += 1
        self.usages.append(None)
        output = {"request": self.requests, "stage": self.stage(messages), "response": None, "error_code": None}
        self.outputs.append(output)
        if self.usage_source:
            self.usage_source.last_usage = None
        try:
            response = self.client.complete(messages, tools)
            if isinstance(response, LLMResponse):
                output["response"] = response.model_dump(mode="json")
            return response
        except Exception:
            output["error_code"] = "model_exception"
            raise
        finally:
            if self.usage_source:
                self.usages[-1] = self.usage_source.last_usage
            output["usage"] = self.usages[-1]

    def cost(self):
        known = [usage for usage in self.usages if usage is not None]
        complete = bool(self.usages) and len(known) == len(self.usages)
        return {"llm_requests": self.requests,
                "api_requests": getattr(self.client, "request_count", None),
                "token_usage": {key: sum(usage[key] for usage in known) if complete else None
                                for key in ["prompt_tokens", "completion_tokens", "total_tokens"]},
                "usage_requests_available": len(known)}


class UsageSDK:
    """Observe provider usage before the unchanged DeepSeek adapter normalizes it."""

    def __init__(self, sdk):
        self.sdk, self.last_usage = sdk, None
        self.chat = SimpleNamespace(completions=SimpleNamespace(create=self.create))

    def create(self, **kwargs):
        self.last_usage = None
        completion = self.sdk.chat.completions.create(**kwargs)
        usage = getattr(completion, "usage", None)
        keys = ["prompt_tokens", "completion_tokens", "total_tokens"]
        if usage is not None and all(type(getattr(usage, key, None)) is int and getattr(usage, key) >= 0 for key in keys):
            self.last_usage = {key: getattr(usage, key) for key in keys}
        return completion

    def close(self):
        self.sdk.close()
