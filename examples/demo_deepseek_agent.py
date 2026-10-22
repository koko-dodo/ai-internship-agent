"""Explicit opt-in only: python -m examples.demo_deepseek_agent --run."""

import argparse

from src.agent import Agent
from src.deepseek import DEFAULT_MODEL, DeepSeekClientError, DeepSeekLLMClient
from src.schemas import ParseJobArguments
from src.tool_registry import ToolRegistry
from src.tools import parse_job


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Real, billable DeepSeek tool-calling demo")
    parser.add_argument("--run", action="store_true", help="Explicitly allow paid API requests")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-calls", type=int, choices=(1, 2, 3), default=3)
    parser.add_argument("--max-tokens", type=int, choices=(128, 256, 512), default=512)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("No API request made. Pass --run to explicitly start the paid demo.")

    # Only this text tool is registered: the demo has no resume/file access.
    registry = ToolRegistry()
    registry.register("parse_job", ParseJobArguments, parse_job)
    task = (
        "请先调用 parse_job 工具提取以下虚构 JD，再依据工具结果用中文简短列出必备和加分技能。"
        "不要自行猜测技能。\n"
        "Title: AI Intern\nCompany: Example\nRequired: Python, SQL\nPreferred: Docker"
    )
    try:
        client = DeepSeekLLMClient(
            model=args.model, max_calls=args.max_calls, max_tokens=args.max_tokens,
        )
    except DeepSeekClientError as exc:
        print(f"无法启动：{exc.code}（请检查 DEEPSEEK_API_KEY 和配置；不会读取 .env）。")
        return 1
    try:
        result = Agent(client, registry, max_steps=args.max_calls).run(task)
        # Log metadata only; never print full history, SDK responses, or keys.
        for event in result.trace:
            if event.event in {"tool_result", "tool_skipped"}:
                print(f"工具：{event.tool_name}；成功：{event.success}；错误码：{event.error_code}")
        print(f"终止状态：{result.status}")
        print(f"API 请求次数：{client.request_count}/{args.max_calls}；每次最大输出 Token：{args.max_tokens}")
        if client.last_error_code:
            print(f"适配器错误码：{client.last_error_code}")
        if result.final_answer:
            print(f"模型最终回答：{result.final_answer}")
        else:
            print(result.message)
        used_tool = any(event.event == "tool_result" and event.success for event in result.trace)
        if result.status == "completed" and not used_tool:
            print("模型未调用工具，本次未完成 Tool Calling 演示。")
        return 0 if result.status == "completed" and used_tool else 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
