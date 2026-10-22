"""Non-streaming DeepSeek adapter using the OpenAI-compatible SDK.

Importing this module never reads credentials or makes a request. Only the
non-thinking API is supported, so the neutral history needs no reasoning data.
"""

import json
import math
import os
from collections.abc import Sequence
from copy import deepcopy
from typing import Any

from openai import APIConnectionError, APIStatusError, APITimeoutError, OpenAI

from .llm import LLMResponse, Message, ToolCall
from .schemas import ToolSchema


DEFAULT_MODEL = "deepseek-flash"
BASE_URL = "https://api.deepseek.com"

ERROR_MESSAGES = {
    "configuration_error": "DeepSeek configuration is invalid or DEEPSEEK_API_KEY is missing.",
    "call_limit": "DeepSeek request limit reached; no request was sent.",
    "invalid_request": "DeepSeek request could not be serialized as JSON.",
    "timeout": "DeepSeek request timed out; it will not be retried automatically.",
    "connection_error": "Unable to connect to DeepSeek; no automatic retry.",
    "api_error": "DeepSeek rejected the request; check account and model configuration.",
    "sdk_error": "DeepSeek SDK request failed unexpectedly.",
    "invalid_tool_arguments": "DeepSeek tool arguments must be a valid JSON object.",
    "invalid_response": "DeepSeek returned an unsupported or malformed response.",
    "response_truncated": "DeepSeek output was truncated; no partial tool call or answer was accepted.",
    "close_error": "Unable to close the DeepSeek SDK client.",
}


class DeepSeekClientError(RuntimeError):
    """Safe diagnostic code and fixed message; never include SDK payloads."""

    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(ERROR_MESSAGES[code])


def _reject_constant(value: str) -> None:
    raise ValueError("Non-JSON numeric constant")


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("Duplicate JSON key")
        result[key] = value
    return result


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, allow_nan=False)


class DeepSeekLLMClient:
    """Implements LLMClient.complete; limits apply across this client's lifetime.

    sdk_client is for dependency injection. Injected clients must also disable
    SDK retries if used outside tests. No dotenv loading, automatic retries,
    request logging, or raw SDK exception propagation is performed here.
    """

    def __init__(
        self, *, model: str = DEFAULT_MODEL, timeout: float = 30.0,
        max_calls: int = 3, max_tokens: int = 512, sdk_client: Any = None,
    ) -> None:
        if (
            not isinstance(model, str) or not model.strip()
            or type(max_calls) is not int or max_calls < 1
            or type(max_tokens) is not int or max_tokens < 1
            or type(timeout) not in (int, float) or not math.isfinite(timeout) or timeout <= 0
        ):
            raise DeepSeekClientError("configuration_error")
        self.model = model
        self.timeout = timeout
        self.max_calls = max_calls
        self.max_tokens = max_tokens
        self.request_count = 0
        self.last_error_code: str | None = None
        if sdk_client is not None:
            self._sdk = sdk_client
        else:
            key = os.environ.get("DEEPSEEK_API_KEY")
            if not key or not key.strip():
                raise DeepSeekClientError("configuration_error")
            try:
                self._sdk = OpenAI(
                    api_key=key, base_url=BASE_URL, timeout=timeout, max_retries=0,
                )
            except Exception:
                raise DeepSeekClientError("configuration_error") from None

    def _fail(self, code: str) -> DeepSeekClientError:
        self.last_error_code = code
        return DeepSeekClientError(code)

    @staticmethod
    def _messages(messages: Sequence[Message]) -> list[dict[str, Any]]:
        converted = []
        for message in messages:
            if message.role == "tool":
                converted.append({
                    "role": "tool", "tool_call_id": message.tool_call_id,
                    "content": _json_dumps(message.tool_result.model_dump(mode="json")),
                })
            elif message.tool_calls:
                converted.append({
                    "role": "assistant", "content": None,
                    "tool_calls": [
                        {"id": call.id, "type": "function", "function": {
                            "name": call.name, "arguments": _json_dumps(call.arguments),
                        }}
                        for call in message.tool_calls
                    ],
                })
            else:
                converted.append({"role": message.role, "content": message.content})
        return converted

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> LLMResponse:
        self.last_error_code = None
        if self.request_count >= self.max_calls:
            raise self._fail("call_limit")
        try:
            request: dict[str, Any] = {
                "model": self.model, "messages": self._messages(messages),
                "max_tokens": self.max_tokens, "timeout": self.timeout,
                "stream": False, "n": 1,
                "extra_body": {"thinking": {"type": "disabled"}},
            }
            if tools:
                request["tools"] = [{"type": "function", "function": {
                    "name": tool.name, "description": tool.description,
                    "parameters": deepcopy(tool.parameters),
                }} for tool in tools]
                request["tool_choice"] = "auto"
            _json_dumps(request)  # Reject non-JSON data before attempting a paid call.
        except Exception:
            raise self._fail("invalid_request") from None

        # Failed and malformed-response attempts consume the budget too.
        self.request_count += 1
        try:
            completion = self._sdk.chat.completions.create(**request)
        except APITimeoutError:
            raise self._fail("timeout") from None
        except APIConnectionError:
            raise self._fail("connection_error") from None
        except APIStatusError:
            raise self._fail("api_error") from None
        except Exception:
            raise self._fail("sdk_error") from None

        try:
            return self._response(completion)
        except DeepSeekClientError as exc:
            raise self._fail(exc.code) from None
        except Exception:
            raise self._fail("invalid_response") from None

    @staticmethod
    def _response(completion: Any) -> LLMResponse:
        if len(completion.choices) != 1:
            raise DeepSeekClientError("invalid_response")
        choice = completion.choices[0]
        if choice.finish_reason == "length":
            raise DeepSeekClientError("response_truncated")
        message = choice.message
        if message.role != "assistant" or getattr(message, "reasoning_content", None):
            raise DeepSeekClientError("invalid_response")
        if message.tool_calls:
            if choice.finish_reason != "tool_calls":
                raise DeepSeekClientError("invalid_response")
            calls = []
            for call in message.tool_calls:
                if call.type != "function":
                    raise DeepSeekClientError("invalid_response")
                try:
                    if not isinstance(call.function.arguments, str):
                        raise ValueError("Tool arguments must be JSON text")
                    arguments = json.loads(
                        call.function.arguments, parse_constant=_reject_constant,
                        object_pairs_hook=_unique_object,
                    )
                    if not isinstance(arguments, dict):
                        raise ValueError("Tool arguments must be an object")
                    _json_dumps(arguments)  # Also reject exponent overflow to infinity.
                except (ValueError, TypeError):
                    raise DeepSeekClientError("invalid_tool_arguments") from None
                calls.append(ToolCall(id=call.id, name=call.function.name, arguments=arguments))
            # Providers may include a text preamble with tool calls. The internal
            # protocol stores only the tool decision, not a premature final answer.
            return LLMResponse(tool_calls=calls)
        if choice.finish_reason != "stop":
            raise DeepSeekClientError("invalid_response")
        return LLMResponse(final_answer=message.content)

    def close(self) -> None:
        try:
            self._sdk.close()
        except Exception:
            raise self._fail("close_error") from None
