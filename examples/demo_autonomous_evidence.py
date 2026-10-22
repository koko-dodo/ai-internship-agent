"""Offline A/B/C by default; paid DeepSeek mode requires --deepseek --run."""

import argparse

from src.autonomy import BudgetedLLMClient, EvidenceGatheringSession, start_cost_aware_matching
from src.evidence_search import EXAMPLES_DIRECTORY, ProjectEvidenceSearch
from src.llm import LLMResponse, MockLLMClient
from src.matching import build_match_report
from src.schemas import JobPosting, SemanticEvidenceEvaluation
from src.tools import read_resume


def response(payload: dict) -> LLMResponse:
    import json
    return LLMResponse(final_answer=json.dumps(payload, ensure_ascii=False))


def offline_session(required: bool, responses: list[LLMResponse], materials=()) -> EvidenceGatheringSession:
    resume = "虚构简历：有 Python 项目经验，未提供其他技能信息。"
    job = JobPosting(title="数据实习生", required_skills=["SQL"] if required else [],
                     preferred_skills=[] if required else ["SQL"])
    report = build_match_report(job, SemanticEvidenceEvaluation.model_validate({"assessments": [{
        "skill": "SQL", "status": "not_found", "quotes": [], "reasoning": "初步简历证据不足。",
    }]}), resume, "demo_resume.txt")
    return EvidenceGatheringSession(
        BudgetedLLMClient(MockLLMClient(responses), max_requests=8), report, resume,
        ProjectEvidenceSearch(materials),
    )


def show(label: str, result) -> None:
    actions = " → ".join(event.action for event in result.trace if event.event == "decision" and event.action)
    print(f"{label}：{actions}")
    print(f"状态：{result.status}；分数：{result.initial_report.score.score:g} → {result.report.score.score:g}；"
          f"检索：{result.searches}；LLM 请求：{result.llm_requests}")
    if result.question:
        print(f"问题：{result.question}")


def offline_demo() -> None:
    print("离线 Mock：以下行动为预设序列，仅演示真实 Python 执行、校验和状态转换。")
    a = offline_session(True, [
        response({"action": "SEARCH", "reason": "必备技能缺证，授权材料读取成本低。", "skill": "SQL", "source": "projects/sql_project.md"}),
        response({"skill": "SQL", "status": "supported", "citations": [{"source": "projects/sql_project.md",
                  "quote": "本人负责 SQL 查询模块，使用 JOIN 和 GROUP BY 汇总借阅记录，"}], "reasoning": "项目文件提供具体查询工作原文。"}),
        response({"action": "FINISH", "reason": "已获取并核验必备技能的原文引用。"}),
    ], ["projects/sql_project.md"])
    show("A", a.run())
    b = offline_session(True, [
        response({"action": "ASK_USER", "reason": "必备技能缺少证据且没有授权材料。", "skill": "SQL", "question": "你能提供本人编写 SQL 查询的项目文件或具体片段吗？"}),
        response({"action": "FINISH", "reason": "用户暂无文件，保留证据不足，不据陈述加分。"}),
    ])
    show("B", b.run())
    show("B 收到回复后", b.resume("我使用过 SQL，但暂时没有可授权的项目文件。"))
    c = offline_session(False, [response({"action": "FINISH", "reason": "仅缺低优先级加分项，无授权材料，继续取证收益较低。"})])
    show("C", c.run())
    reliability_demo()
    action_validation_demo()


def _reliability_inputs(sql_skill="SQL查询", docker_skill="Docker部署"):
    resume = read_resume(str(EXAMPLES_DIRECTORY / "matching_resume.md"), allowed_directory=EXAMPLES_DIRECTORY)
    jd = read_resume(str(EXAMPLES_DIRECTORY / "matching_job.md"), allowed_directory=EXAMPLES_DIRECTORY)
    project = read_resume(str(EXAMPLES_DIRECTORY / "projects/sql_project.md"), allowed_directory=EXAMPLES_DIRECTORY)
    project_lines = project.splitlines()
    common = next(line for line in resume.splitlines() if "使用 Python 和 Pandas" in line)
    sql = next(line for line in resume.splitlines() if "完成 SQL 基础课程" in line)
    report = build_match_report(
        JobPosting(title="数据实习生", required_skills=["Python", "Pandas", sql_skill, "Git"],
                   preferred_skills=[docker_skill, "PyTorch"], description=jd),
        SemanticEvidenceEvaluation.model_validate({"assessments": [
            {"skill": skill, "status": "supported", "quotes": [common], "reasoning": "原文有具体实践。"}
            for skill in ["Python", "Pandas", "Git"]
        ] + [{"skill": sql_skill, "status": "partial", "quotes": [sql], "reasoning": "SQL 基础实践，业务子要求缺证。"}]
          + [{"skill": skill, "status": "not_found", "quotes": [], "reasoning": "当前证据不足。"} for skill in [docker_skill, "PyTorch"]]}),
        resume, "matching_resume.md",
    )
    return resume, project_lines, report


def reliability_demo() -> None:
    """Replay the logged failure pattern with actual example-file validation."""
    resume, project_lines, report = _reliability_inputs()
    search = {"action": "SEARCH", "reason": "补充 SQL 项目实践。", "skill": "SQL查询", "source": "projects/sql_project.md"}
    client = BudgetedLLMClient(MockLLMClient([
        response(search),
        response({"skill": "SQL查询", "status": "partial", "reasoning": "有 SQL 实践但真实业务条件未满足。",
                  "citations": [{"source": "projects/sql_project.md", "quote": project_lines[index]} for index in [2, 5]]}),
        response(search),  # Simulate one ignored constraint; Python blocks any reread.
        response({"action": "ASK_USER", "reason": "已无可用的新检索组合，需核实业务实践。", "skill": "SQL查询",
                  "question": "能否提供 SQL 用于真实业务数据的项目文件或具体场景？"}),
        response({"action": "FINISH", "reason": "未取得新的业务文件，保持已验证的部分匹配。"}),
    ]), max_requests=8)
    session = EvidenceGatheringSession(client, report, resume,
                                      ProjectEvidenceSearch(["projects/sql_project.md"], max_searches=1), max_rounds=3)
    show("D 可靠性复现", session.run())
    show("D 最后一轮提问后恢复", session.resume("我做过课程 SQL 项目，但暂时没有真实业务项目文件。"))
    print("D 校验：SQL查询保持 partial；业务环境仍待核实；重复 SEARCH 未再次读取文件。")


def action_validation_demo() -> None:
    """Latest three-search log plus a deliberately invalid ASK and correction."""
    resume, lines, report = _reliability_inputs("SQL", "Docker")
    responses = [response({"action": "SEARCH", "reason": "检查授权项目材料。", "skill": skill,
                           "source": "projects/sql_project.md"}) for skill in ["SQL", "Docker", "PyTorch"]]
    responses.insert(1, response({"skill": "SQL", "status": "partial", "reasoning": "实践存在，业务环境仍待核实。",
                                  "citations": [{"source": "projects/sql_project.md", "quote": lines[i]} for i in [2, 5]]}))
    question = {"action": "ASK_USER", "reason": "项目材料未解决所有疑问。",
                "question": "请提供 SQL 用于真实业务数据的具体场景或项目文件。"}
    responses.extend([
        response({**question, "skill": "到岗时间"}),  # Unsupported target; never infer a skill.
        response({**question, "skill": "SQL"}),
        response({"action": "FINISH", "reason": "没有新文件佐证，保留已核验的部分匹配。"}),
    ])
    session = EvidenceGatheringSession(BudgetedLLMClient(MockLLMClient(responses), 8), report, resume,
                                      ProjectEvidenceSearch(["projects/sql_project.md"], 3))
    result = session.run()
    show("E 最新轨迹与参数纠正", result)
    hits = "，".join(f"{event.skill}={event.candidate_count}" for event in result.trace if event.event == "search")
    errors = ",".join(event.error_code for event in result.trace if event.event == "decision" and event.error_code)
    print(f"E 检索候选：{hits}；参数反馈：{errors}；SQL 状态：{result.context['status']}。")
    show("E 示例用户回复后", session.resume("暂时没有可以授权的真实业务项目文件。"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--deepseek", action="store_true")
    parser.add_argument("--run", action="store_true", help="Explicitly authorize paid requests")
    parser.add_argument("--authorize", action="append", default=[], help="Individual project file relative to examples/; repeatable")
    parser.add_argument("--model", default=None)
    parser.add_argument("--max-calls", type=int, choices=(8, 12, 16), default=12)
    parser.add_argument("--max-rounds", type=int, choices=(3, 5, 7), default=5)
    parser.add_argument("--max-searches", type=int, choices=(0, 1, 2, 3), default=3)
    replies = parser.add_mutually_exclusive_group()
    replies.add_argument("--answer", default=None, help="Explicit user reply, used only if the session asks a question")
    replies.add_argument("--interactive", action="store_true", help="Read one real reply after ASK_USER, within the same session")
    args = parser.parse_args(argv)
    if not args.deepseek:
        if args.run or args.authorize or args.answer is not None or args.interactive:
            parser.error("Paid-demo options require --deepseek")
        offline_demo()
        return 0
    if not args.run:
        parser.error("No paid request made. DeepSeek mode requires --deepseek --run")
    # Import/construct the real SDK only after explicit opt-in.
    from src.deepseek import DEFAULT_MODEL, DeepSeekClientError, DeepSeekLLMClient
    try:
        ProjectEvidenceSearch(args.authorize, max_searches=args.max_searches)  # Grant preflight, no API.
        jd = read_resume(str(EXAMPLES_DIRECTORY / "matching_job.md"), allowed_directory=EXAMPLES_DIRECTORY)
    except (OSError, ValueError):
        print("授权材料或 JD 不合法；未启动 API 请求。")
        return 1
    try:
        client = DeepSeekLLMClient(model=args.model or DEFAULT_MODEL, max_calls=args.max_calls, max_tokens=2048)
    except DeepSeekClientError as exc:
        print(f"无法启动：{exc.code}；请在进程环境中配置 DEEPSEEK_API_KEY。")
        return 1
    try:
        session = start_cost_aware_matching(
            client, str(EXAMPLES_DIRECTORY / "matching_resume.md"), jd, args.authorize,
            max_llm_requests=args.max_calls, max_rounds=args.max_rounds, max_searches=args.max_searches,
        )
        result = session.run()
        show("DeepSeek", result)
        if result.status == "waiting_for_user" and args.answer is not None:
            result = session.resume(args.answer)
            show("收到用户回复后", result)
        elif result.status == "waiting_for_user" and args.interactive:
            answer = input("请输入实际回复（留空则保持等待）：").strip()
            if answer:
                result = session.resume(answer)
                show("收到用户回复后", result)
        if result.status == "waiting_for_user":
            print("等待真实用户回答；不会继续调用模型或假装完成。进程退出后不保存会话。")
        # Intentional report artifact, not a diagnostic log.
        print(result.model_dump_json(indent=2))
        return 0 if result.status in {"finished", "waiting_for_user"} else 1
    except Exception:
        print("初步匹配或自主取证未完成；未记录原始异常或私密内容。")
        return 1
    finally:
        client.close()


if __name__ == "__main__":
    raise SystemExit(main())
