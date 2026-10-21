"""Run with: .venv/bin/python -m examples.demo_agent (no API or private data)."""

import json

from src.agent import Agent
from src.llm import LLMResponse, MockLLMClient, ToolCall
from src.tool_registry import create_tool_registry


def main() -> None:
    jd_text = "Title: AI Intern\nRequired: Python, SQL\nPreferred: Docker"
    task = "请提取示例 JD 的必备技能和加分技能。"
    client = MockLLMClient([
        LLMResponse(tool_calls=[ToolCall(
            id="demo-job", name="parse_job", arguments={"jd_text": jd_text},
        )]),
        LLMResponse(final_answer="工具调用已完成。此回复为 Mock 预设，不代表真实模型推理。"),
    ])
    result = Agent(client, create_tool_registry(), max_steps=3).run(task)
    print(f"用户任务：{task}")
    for message in result.messages:
        if message.role == "assistant" and message.tool_calls:
            for call in message.tool_calls:
                print(f"Mock 请求工具：{call.name} (id={call.id})")
        elif message.role == "tool":
            # This demo prints only its synthetic public JD result, never a resume.
            print(f"Python Tool Result (id={message.tool_call_id})："
                  + json.dumps(message.tool_result.model_dump(), ensure_ascii=False))
        elif message.role == "assistant":
            print(f"Mock 最终回复：{message.content}")
    print(f"终止状态：{result.status}；模型调用轮数：{result.steps}")
    if result.status != "completed":
        raise SystemExit(1)


if __name__ == "__main__":
    main()
