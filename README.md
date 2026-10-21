# AI Internship Agent

当前包含离线工具层、供应商无关的 LLM 接口和轻量 Agent Loop。
使用 Python 3.12、Pydantic 2、pytest，不使用 Agent 框架。
默认测试与 Mock Demo 均离线；DeepSeek 真实 API Demo 必须显式启动。

## 工具接口

- `read_resume(file_path, *, allowed_directory=...) -> str`：UTF-8 TXT/Markdown。
  保留原有单参数用法，默认仅允许项目 `examples/`；相对路径仍相对于当前工作目录。
  支持配置一个允许目录，解析 `..` 和符号链接后检查真实路径归属，并检查真实文件扩展名。
- `parse_job(jd_text) -> JobPosting`：提取 `Title/职位`、`Company/公司` 等标签，
  无职位标签时取首个非公司非空行；保留完整原始 JD。
  通过 `src/tools.py` 的固定技能词表、别名和 `Required/任职要求`、
  `Preferred/加分项` 等行首标签区分技能。无分区的命中默认为必备；同一技能必备优先。
  技能顺序按原文行序、同行词表序排列，不重复。
- `find_evidence(resume_text, skills) -> list[SkillEvidence]`：逐关键词返回原文匹配行，
  保留行内空格（不包含换行符）；无证据时 `found=False, evidence=[]`。
  关键词不区分大小写，按字面匹配，不做别名扩展；ASCII 关键词要求单词边界，
  避免 `SQL` 匹配 `MySQL`，同时支持中文紧邻英文技能。

## 注册与执行

```python
from src.tool_registry import create_tool_registry

registry = create_tool_registry()  # 也可由应用代码指定 allowed_directory
result = registry.execute("read_resume", {"file_path": "examples/resume.txt"})
print(result.model_dump_json())
```

`ToolRegistry()` 初始为空；只有显式 `register(name, arguments_model, handler)` 的工具可执行。
标准工厂显式注册上述三个工具。允许目录由应用配置，工具参数无法覆盖。
Pydantic 严格拒绝参数类型错误、额外字段、缺失字段及空白关键词。
执行结果统一为 `tool_name/success/data/error`，成功数据可 JSON 序列化，
错误包含稳定 `code` 和说明，参数验证错误不回显输入值。
直接调用工具函数时仍抛出 Python/Pydantic 异常，执行器负责转为统一结果。

`registry.get_tool_schemas()` 从每个已注册工具的参数模型直接生成 JSON Schema，
同时提供名称和描述，不单独维护一套模型可用工具。`register()` 新增可选的
`description=` 关键字，原有三个位置参数和 `execute()` 接口保持兼容。

## LLM 接口与 Mock

`src/llm.py` 的供应商无关类型：

- `ToolCall(id, name, arguments)`：一次调用的唯一 ID、工具名和参数对象。
- `LLMResponse(final_answer=...)` 或 `LLMResponse(tool_calls=[...])`：严格二选一；
  拒绝空回答、空决策、重复调用 ID 和同时给出最终回答与工具调用。
- `Message`：用户文本、助手决策或工具结果；工具消息通过 `tool_call_id` 关联调用。
- `LLMClient.complete(messages, tools) -> LLMResponse`：同步 Protocol，
  接收完整历史及 Registry 生成的 `ToolSchema`。适配器负责转换供应商协议。
- `MockLLMClient(responses)`：依次返回预设响应或抛出预设异常，序列耗尽时明确报错。
  `requests` 保存输入的深拷贝，便于测试历史和 ID 对应关系。

Mock 不读取或理解任务，不根据工具结果自主推理。多轮测试中后续调用参数也由测试预设。
它验证的是控制流程、消息传递和错误策略，不能证明真实模型会正确选工具、理解结果或生成可靠分析。

## Agent Loop

```python
from src.agent import Agent
from src.llm import LLMResponse, MockLLMClient, ToolCall
from src.tool_registry import create_tool_registry

client = MockLLMClient([
    LLMResponse(tool_calls=[ToolCall(
        id="job-1", name="parse_job", arguments={"jd_text": "AI Intern\nRequired: Python"},
    )]),
    LLMResponse(final_answer="工具调用已完成（Mock 预设回复）。"),
])
result = Agent(client, create_tool_registry(), max_steps=4).run("提取 JD 技能")
print(result.status, result.final_answer)
```

`Agent(llm_client, tool_registry, max_steps=8).run(task)` 的每轮流程：

1. 将用户任务和此前历史的副本，以及当前 Registry 的工具描述传给 Client。
2. 验证模型响应；记录决策，并将助手消息加入历史。
3. 若有最终回答，以 `completed` 结束；否则按列表顺序调用 `ToolRegistry.execute()`。
4. 每个结果以独立工具消息加入历史，保留调用 ID，然后进入下一轮。

同轮多个调用顺序执行，不做并行调度。若一个调用需要前一个调用的输出，应由模型在下一轮发起。
调用 ID 要求整次运行唯一，重复或非法响应以 `model_error / invalid_model_response` 停止，
在响应验证完成前不执行该轮任何工具。

`max_steps` 是正整数，表示最多调用模型多少轮（包含最终回答轮），不是工具数量。
最后一轮请求的工具仍会执行并记录结果；若没有最终回答则以 `step_limit`、
`max_steps_exceeded` 结束，`final_answer=None`，不伪装成功。
本实现不限制单次供应商请求耗时或同轮调用数量；真实适配器需要配置请求超时。

## 失败策略与调试

| 情况 | 行为 |
| --- | --- |
| `invalid_arguments`、`unknown_tool`、`invalid_input` | 将失败结果反馈给模型；允许下轮修正，仍受最大轮数约束 |
| `access_denied` | 立即终止整次任务，不允许改路径重试 |
| `file_not_found` | 立即终止，请用户提供正确文件，不扫描目录 |
| 编码、I/O、未预期执行异常及其他工具错误 | 默认终止，状态 `tool_error` |
| Client 抛异常（含 Mock 耗尽） | 状态 `model_error`、错误码 `model_exception`；不记录异常原文 |
| 模型响应格式错误、调用 ID 重用 | 状态 `model_error`、错误码 `invalid_model_response` |
| 用完模型调用轮数 | 状态 `step_limit`、错误码 `max_steps_exceeded` |

工具致命失败后，同批后续调用不执行，但仍生成 ID 对应的 `not_executed` 结果，
保证历史中的每个工具请求都能找到对应结果；此前已完成的调用不回滚。
下一轮不会调用模型，也不会自主扫描文件或修改文件访问配置。

`AgentRunResult` 提供 `status`、`steps`、`final_answer`、`message`、`error_code`、
`messages` 和 `trace`。`trace` 只记录轮次、决策类型、已注册工具名、执行成功与否和错误码；
未注册名称统一记为 `<unregistered>`，避免模型把私密文本放入工具名后进入日志。
轨迹不包含调用参数、文件路径、结果正文、最终回答或异常原文，Agent 本身不打印日志。
`messages` 和 `MockLLMClient.requests` 是完整的模型上下文，可能含简历原文，
不能当日志打印；不要直接将整个 `AgentRunResult.model_dump()` 写入日志。

## 离线 Demo

从项目根目录运行：

```sh
.venv/bin/python -m examples.demo_agent
```

Demo 使用虚构 JD，实际由 Agent 调用 `parse_job`，打印真实工具结果，再返回预设的 Mock 文本。
只打印这份公开示例数据，不读取简历或 `.env`；没有绕过 Agent 直接返回报告。
正常结束状态为 `completed`，模型调用轮数为 2。

## DeepSeek API 适配器

`src/deepseek.py` 中的 `DeepSeekLLMClient` 实现同一个
`complete(messages, tools) -> LLMResponse` 协议，无需修改 Agent Loop、Mock 或工具接口。
模块导入不读凭据、不发请求。真实 Client 在构造时仅从进程环境读取 `DEEPSEEK_API_KEY`，
不加载或修改 `.env`，不使用 `OPENAI_API_KEY`。代码不会打印或记录密钥。

适配器使用 OpenAI 兼容 SDK，固定连接 `https://api.deepseek.com`。
依赖列在 `requirements-deepseek.txt`，当前离线测试使用已安装的 OpenAI SDK 3.35.1。
若环境没有 SDK，可自行安装该依赖文件；本次开发没有安装新依赖。

协议转换：

- 用户文本和最终助手回答转换为 `role/content` 消息。
- Registry 的 `ToolSchema` 原样映射到 `type=function` 和
  `function.name/description/parameters`，不另外维护工具定义。
- 助手工具请求保留 `id`、函数名，将参数对象编码为 JSON 字符串。
- 工具结果编码为包含 `tool_name/success/data/error` 的 JSON 字符串，
  以 `role=tool`、原始 `tool_call_id` 回传；工具失败同样回传。
- SDK 返回的所有函数调用转换为 `ToolCall`，保留每个 ID、工具名和 JSON 参数对象。
  内容字段中的工具调用前言不会被当作最终回答；没有工具调用时才接受最终文本。
- 同轮多个调用及多轮消息历史由现有 Agent 顺序执行、关联和保存。

默认模型为 `deepseek-flash`，可通过构造参数或 Demo 的 `--model` 指定其他可用模型。
显式传入 `thinking.type=disabled`，只支持非思考模式，不保留 `reasoning_content`。
这与现有供应商中立消息结构兼容，避免为了此适配器修改 Agent。
格式参考 [DeepSeek Tool Calls 文档](https://api-docs.deepseek.com/guides/tool_calls/)
和 [Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)。

`DeepSeekClientError.code` 使用固定诊断码，异常消息不包含原始 SDK 错误或响应正文：

| 诊断码 | 含义 |
| --- | --- |
| `configuration_error` | 缺少环境密钥或配置无效 |
| `timeout` / `connection_error` | SDK 超时或无法连接，不自动重试 |
| `api_error` / `sdk_error` | API 拒绝请求或 SDK 未预期异常 |
| `invalid_tool_arguments` | 参数 JSON 不合法、不是对象、含重复键或非有限数值 |
| `invalid_response` | 响应为空、ID 无效或重复、决策格式异常、出现非预期推理内容等 |
| `response_truncated` | `finish_reason=length`，拒绝执行部分工具调用或接受截断回答 |
| `invalid_request` | 本地历史无法编码为 JSON，请求未发出 |
| `call_limit` | Client 的请求次数额度耗尽，请求未发出 |
| `close_error` | SDK 资源关闭失败 |

适配器对非法工具 JSON 直接终止本轮，不猜测、修复参数或执行部分调用。
合法 JSON 中的业务字段错误仍由 Tool Executor 验证，可按现有策略反馈模型修正。
为保持接口稳定，适配器异常进入 Agent 后仍表现为 `model_error / model_exception`；
调用方可查看 `client.last_error_code` 获取安全的细分原因。

默认每个 Client 实例最多尝试 3 次 SDK 请求，每次最多输出 512 Token，SDK 超时配置为 30 秒。
真实 SDK 配置 `max_retries=0`，没有隐藏重试；超时、连接失败及异常响应也消耗一次请求额度。
额度跨同一 Client 的多次 `run()` 累计，不自动重置。
`sdk_client=` 支持测试依赖注入；若自行注入真实 SDK，调用方也必须禁用其自动重试。

## 手动启动真实 DeepSeek Demo

先在当前 Shell 安全设置并导出 `DEEPSEEK_API_KEY`，再从项目根目录手动执行：

```sh
.venv/bin/python -m examples.demo_deepseek_agent --run
```

也可使用本地已经验证可用的模型名称：

```sh
.venv/bin/python -m examples.demo_deepseek_agent --run --model MODEL_NAME --max-calls 2 --max-tokens 256
```

不传 `--run` 时会直接退出，不构造 API Client。Demo 只注册 `parse_job`，
只发送写在代码中的虚构 JD，不读取简历、不具备文件工具权限。
模型根据任务动态请求工具，Python 执行后把真实结果交回模型生成最终回答。
若模型直接回答而没有调用工具，Demo 会明确提示演示未完成，并返回非零退出码。

Demo 最多允许 3 次请求，`--max-calls` 只能取 1/2/3，`--max-tokens` 只能取 128/256/512，
并将 Agent 的模型轮次上限设为同样的请求次数。达到轮次上限、API 异常或预算耗尽均不会自动续跑。
只打印执行元数据、请求次数、安全错误码和模型最终回答，不打印完整历史或原始 API 响应。
调用次数和输出 Token 限制不是精确货币预算：输入历史也会计费，失败请求是否计费由服务商决定。
本次只完成代码和离线测试，未执行付费 Demo；首次真实多轮调用仍待用户手动验证。

## 离线测试

在已安装 Pydantic 2 和 pytest 的 Python 3.12 环境运行：

```sh
.venv/bin/python -m pytest
```

`pytest.ini` 默认只收集 `tests/`。根目录历史 `test_direct.py` 和 `test_gemini.py`
在导入时会加载环境密钥并发起真实 API 请求，因此不纳入默认测试；不要显式运行它们。
根目录的 `test_deepseek.py` 也不在测试收集范围内，本次未读取、修改或运行该脚本。
Agent 与 LLM 测试使用 Mock，覆盖直接回答、多轮/同轮多调用、ID 关联、可恢复错误、
文件错误后的停止与取消、执行上限、模型异常和轨迹脱敏。工具层原有测试继续运行。
DeepSeek 测试使用 Fake SDK、真实 SDK 响应类型及合成异常，不读取真实密钥或访问真实 API；
还通过替换 SDK 的实际请求方法，防止这些适配器测试意外触网。

## 设计限制

JD 提取是可测试的文本规则，词表外技能、否定、熟练度、隐含要求和复杂格式不作语义判断。
证据只是原文提及，不代表技能得到验证，例如“未使用 Python”仍会匹配。
文件工具只处理可信本地应用配置下的普通文本；路径检查和读取之间未实现操作系统级原子锁定，
不用于存在并发恶意符号链接替换的多租户文件系统。暂无文件大小限制或 PDF/DOCX 支持。
本阶段不包含前端或数据库；`completed` 仅代表模型返回最终回答，
不自动证明回答正确或用户目标已经实质达成。
DeepSeek 适配器目前仅支持同步、非流式、非思考的函数调用；不启用服务商 Beta strict 模式，
工具参数仍由本地 Pydantic 验证。不实现请求自动重试或整体货币预算，真实网络兼容性尚未验证。

后续对接 Gemini 或 Ollama 时，实现满足 `LLMClient.complete()` 的适配器：
将中立消息和 `ToolSchema` 转换为供应商请求，将最终文本或一个/多个工具请求转换为
`LLMResponse`，解析参数 JSON，保留 ID，并正确回传含错误的 `ToolResult`。
若供应商缺少调用 ID，由适配器生成稳定且不重复的 ID 并维护映射。
适配器还需配置超时、供应商错误处理及凭据注入，并验证其支持的 JSON Schema 子集；
供应商异常不得携带密钥或完整请求进入日志。
