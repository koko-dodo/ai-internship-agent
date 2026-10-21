"""A synchronous, bounded tool-calling loop with fail-closed file errors."""

from typing import Literal

from pydantic import BaseModel, Field

from .llm import LLMClient, LLMResponse, Message
from .schemas import ToolError, ToolResult
from .tool_registry import ToolRegistry


class TraceEvent(BaseModel):
    """Loggable metadata only. Never add prompts, arguments, or tool output."""

    step: int
    event: Literal["decision", "tool_result", "tool_skipped", "termination"]
    decision: Literal["tool_calls", "final_answer"] | None = None
    tool_name: str | None = None
    success: bool | None = None
    error_code: str | None = None


class AgentRunResult(BaseModel):
    status: Literal["completed", "tool_error", "model_error", "step_limit"]
    steps: int
    final_answer: str | None = Field(default=None, repr=False)
    message: str
    error_code: str | None = None
    messages: list[Message] = Field(repr=False)
    trace: list[TraceEvent]


# Only these errors allow another model decision. All other tool errors stop.
RECOVERABLE_ERRORS = frozenset({"invalid_arguments", "unknown_tool", "invalid_input"})
STOP_MESSAGES = {
    "access_denied": "文件访问被拒绝，任务已停止；不会尝试其他路径。",
    "file_not_found": "文件不存在，任务已停止。请提供正确的文件路径；不会扫描其他目录。",
}


class Agent:
    def __init__(
        self, llm_client: LLMClient, tool_registry: ToolRegistry, max_steps: int = 8
    ) -> None:
        if type(max_steps) is not int or max_steps < 1:
            raise ValueError("max_steps must be a positive integer")
        self.llm_client = llm_client
        self.tool_registry = tool_registry
        self.max_steps = max_steps

    def run(self, task: str) -> AgentRunResult:
        """Each step is one LLM call, followed by its sequential tool batch.

        Histories contain original user/tool data and must not be used as logs.
        A fatal tool result cancels the rest of its batch and the entire run.
        """
        messages = [Message(role="user", content=task)]
        trace: list[TraceEvent] = []
        seen_call_ids: set[str] = set()

        def finish(
            status: Literal["completed", "tool_error", "model_error", "step_limit"],
            step: int, message: str, error_code: str | None = None,
            final_answer: str | None = None,
        ) -> AgentRunResult:
            trace.append(TraceEvent(
                step=step, event="termination", success=status == "completed",
                error_code=error_code,
            ))
            return AgentRunResult(
                status=status, steps=step, final_answer=final_answer, message=message,
                error_code=error_code, messages=messages, trace=trace,
            )

        for step in range(1, self.max_steps + 1):
            tool_schemas = self.tool_registry.get_tool_schemas()
            registered_names = {schema.name for schema in tool_schemas}
            try:
                response = self.llm_client.complete(
                    [message.model_copy(deep=True) for message in messages],
                    tool_schemas,
                )
            except Exception:
                # Provider exceptions may include prompts or credentials.
                return finish("model_error", step, "模型调用失败，任务已停止。", "model_exception")
            try:
                if not isinstance(response, LLMResponse):
                    raise ValueError("Client must return LLMResponse")
                # Revalidate even constructed/mutated Pydantic responses.
                response = LLMResponse.model_validate(response.model_dump(), strict=True)
                if any(call.id in seen_call_ids for call in response.tool_calls):
                    raise ValueError("Tool call ID reused across steps")
            except Exception:
                return finish(
                    "model_error", step, "模型返回的响应格式或调用 ID 无效。", "invalid_model_response"
                )

            trace.append(TraceEvent(
                step=step, event="decision",
                decision="tool_calls" if response.tool_calls else "final_answer",
            ))
            messages.append(Message(
                role="assistant", content=response.final_answer, tool_calls=response.tool_calls,
            ))
            if response.final_answer is not None:
                return finish(
                    "completed", step, "模型已返回最终回答。", final_answer=response.final_answer
                )

            fatal_code: str | None = None
            for call in response.tool_calls:
                seen_call_ids.add(call.id)
                skipped = fatal_code is not None
                if skipped:
                    result = ToolResult(
                        tool_name=call.name, success=False,
                        error=ToolError(code="not_executed", message="Task stopped; call was not executed"),
                    )
                else:
                    try:
                        result = self.tool_registry.execute(call.name, call.arguments)
                    except Exception:
                        # Custom executors must not leak their exception text either.
                        result = ToolResult(
                            tool_name=call.name, success=False,
                            error=ToolError(code="execution_error", message="Tool execution failed unexpectedly"),
                        )
                messages.append(Message(role="tool", tool_call_id=call.id, tool_result=result))
                code = result.error.code if result.error else None
                trace.append(TraceEvent(
                    step=step, event="tool_skipped" if skipped else "tool_result",
                    # An invented tool name may itself echo private model input.
                    tool_name=call.name if call.name in registered_names else "<unregistered>",
                    success=result.success, error_code=code,
                ))
                if not skipped and not result.success and code not in RECOVERABLE_ERRORS:
                    fatal_code = code or "execution_error"
            if fatal_code is not None:
                return finish(
                    "tool_error", step,
                    STOP_MESSAGES.get(fatal_code, "工具执行失败，任务已停止；请检查输入或工具配置。"),
                    fatal_code,
                )

        return finish(
            "step_limit", self.max_steps, "已达到最大模型调用轮数，任务未完成。", "max_steps_exceeded"
        )
