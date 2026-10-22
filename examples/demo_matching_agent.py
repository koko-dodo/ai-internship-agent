"""Explicitly opt in: python -m examples.demo_matching_agent --run."""

import argparse
from pathlib import Path

from src.agent import Agent
from src.deepseek import DEFAULT_MODEL, DeepSeekClientError, DeepSeekLLMClient
from src.matching import EvidenceBasedMatcher, create_matching_registry
from src.schemas import EvidenceMatchReport
from src.tools import read_resume


EXAMPLES = Path(__file__).resolve().parent


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Billable, single-resume evidence matching demo")
    parser.add_argument("--run", action="store_true", help="Explicitly allow real DeepSeek API calls")
    parser.add_argument("--resume", default=str(EXAMPLES / "matching_resume.md"))
    parser.add_argument("--jd", default=str(EXAMPLES / "matching_job.md"))
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--max-steps", type=int, choices=(2, 3, 4), default=3)
    parser.add_argument("--max-calls", type=int, choices=(4, 6, 8), default=6)
    parser.add_argument("--max-tokens", type=int, choices=(1024, 2048, 4096), default=2048)
    args = parser.parse_args(argv)
    if not args.run:
        parser.error("No API request made. Explicitly pass --run to start this paid demo.")
    try:
        # Reject unauthorized/missing inputs before constructing the real client.
        jd_text = read_resume(args.jd, allowed_directory=EXAMPLES)
        read_resume(args.resume, allowed_directory=EXAMPLES)
    except (OSError, ValueError):
        print("输入无法读取：请提供 examples/ 内的 UTF-8 TXT/Markdown 文件。")
        return 1
    try:
        client = DeepSeekLLMClient(
            model=args.model, max_calls=args.max_calls, max_tokens=args.max_tokens,
        )
    except DeepSeekClientError as exc:
        print(f"无法启动：{exc.code}；请在进程环境中配置 DEEPSEEK_API_KEY。")
        return 1
    try:
        matcher = EvidenceBasedMatcher(client, args.resume, jd_text, allowed_directory=EXAMPLES)
        result = Agent(client, create_matching_registry(matcher), max_steps=args.max_steps).run(
            "请调用 match_resume_to_job，对应用已绑定的一份简历和 JD 生成基于原文证据的匹配报告。"
            "不要自行提供文件、替换内容或分数。工具成功后简短确认完成。"
        )
        print(f"Agent 状态：{result.status}；模型轮数：{result.steps}")
        print(f"API 请求次数（含工具内语义请求）：{client.request_count}/{args.max_calls}")
        reports = [
            message.tool_result.data for message in result.messages
            if message.role == "tool" and message.tool_result.success
            and message.tool_result.tool_name == "match_resume_to_job"
        ]
        if result.status != "completed" or not reports:
            print("未完成端到端匹配，不输出成功报告。")
            if client.last_error_code:
                print(f"适配器错误码：{client.last_error_code}")
            return 1
        report = EvidenceMatchReport.model_validate(reports[-1])
        # This is the verified tool report, never the untrusted assistant final text.
        # It intentionally contains evidence from the user-selected input files.
        print(report.model_dump_json(indent=2))
        return 0
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
