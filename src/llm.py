"""Provider-neutral contracts and a scripted offline client; no API imports."""

from collections.abc import Sequence
from typing import Any, Literal, Protocol, Self

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .schemas import ToolResult, ToolSchema


class ProtocolModel(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid")


class ToolCall(ProtocolModel):
    id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(repr=False)

    @model_validator(mode="after")
    def nonblank_identifiers(self) -> Self:
        if not self.id.strip() or not self.name.strip():
            raise ValueError("Tool call ID and name must not be blank")
        return self


class LLMResponse(ProtocolModel):
    final_answer: str | None = Field(default=None, repr=False)
    tool_calls: list[ToolCall] = Field(default_factory=list)

    @model_validator(mode="after")
    def exactly_one_decision(self) -> Self:
        if (self.final_answer is not None) == bool(self.tool_calls):
            raise ValueError("Return either a final answer or nonempty tool calls")
        if self.final_answer is not None and not self.final_answer.strip():
            raise ValueError("Final answer must not be blank")
        ids = [call.id for call in self.tool_calls]
        if len(ids) != len(set(ids)):
            raise ValueError("Tool call IDs must be unique")
        return self


class Message(ProtocolModel):
    role: Literal["user", "assistant", "tool"]
    content: str | None = Field(default=None, repr=False)
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    tool_result: ToolResult | None = Field(default=None, repr=False)

    @model_validator(mode="after")
    def valid_role_payload(self) -> Self:
        if self.role == "tool":
            if not self.tool_call_id or not self.tool_call_id.strip() or self.tool_result is None:
                raise ValueError("Tool messages require a call ID and result")
            if self.content is not None or self.tool_calls:
                raise ValueError("Tool messages only contain their result")
        else:
            if self.tool_call_id is not None or self.tool_result is not None:
                raise ValueError("Only tool messages have a result and call ID")
            if self.role == "user":
                if self.tool_calls or self.content is None or not self.content.strip():
                    raise ValueError("User messages require nonblank text only")
            else:
                LLMResponse(final_answer=self.content, tool_calls=self.tool_calls)
        return self


class LLMClient(Protocol):
    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> LLMResponse:
        """Return tool requests or a final answer; adapters normalize API data."""
        ...


class LLMRequest(ProtocolModel):
    """Test inspection only: messages can contain sensitive user data."""

    messages: list[Message] = Field(repr=False)
    tools: list[ToolSchema]


class MockLLMExhaustedError(RuntimeError):
    pass


class MockLLMClient:
    """Replay responses/exceptions in order; this does not perform reasoning.

    requests stores deep snapshots for assertions, not for logging. A new Mock
    should be created for a new script/run; exhaustion is an explicit error.
    """

    def __init__(self, responses: Sequence[LLMResponse | Exception]) -> None:
        self._responses = [
            item.model_copy(deep=True) if isinstance(item, LLMResponse) else item
            for item in responses
        ]
        self._index = 0
        self.requests: list[LLMRequest] = []

    def complete(
        self, messages: Sequence[Message], tools: Sequence[ToolSchema]
    ) -> LLMResponse:
        self.requests.append(LLMRequest(
            messages=[message.model_copy(deep=True) for message in messages],
            tools=[tool.model_copy(deep=True) for tool in tools],
        ))
        if self._index >= len(self._responses):
            raise MockLLMExhaustedError("Mock response sequence exhausted")
        response = self._responses[self._index]
        self._index += 1
        if isinstance(response, Exception):
            raise response
        return response.model_copy(deep=True)
