# AI Internship Agent

当前包含离线工具层、供应商无关的 LLM 接口、轻量 Agent Loop、基于证据的岗位匹配，
以及可暂停恢复的成本约束补充取证。
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
单工具 DeepSeek Demo 已由用户完成真实调用验证。下述 Day 4 匹配 Demo 是独立入口，
本次开发只做离线测试，其真实调用仍需用户手动启动。

## Day 4：Evidence-Based Job Matching

只处理一份 TXT/Markdown 简历和一段 JD，不爬取岗位、不批量处理文件。
规则版 `parse_job` 保留原接口，是基础工具与后续对照 Baseline；Day 4 使用语义提取。

模块职责：

- `schemas.py`：新增语义提取、评估提案、原文引用、匹配状态、分数和完整报告模型。
  原有 `JobPosting`、`MatchResult` 和工具参数模型保持兼容。
- `matching.py`：`EvidenceBasedMatcher` 发起两次语义请求；`validate_quote` 精确定位引用；
  `build_match_report` 校验证据并构建报告；`score_matches` 仅根据结构化状态计算分数。
- `tool_registry.py` / `agent.py`：保持不变，负责显式注册、参数校验、执行及有界模型循环。
- `llm.py` / `deepseek.py`：保持不变，通过同一接口提供 Mock 或真实 DeepSeek Client。
- `examples/demo_matching_agent.py`：将服务接入 Agent，展示经过 Python 校验的工具报告。

**最小工具扩展**：新增 `match_resume_to_job`，由 `create_matching_registry(matcher)` 显式注册。
它的参数模型是空对象，`additionalProperties=false`。应用预先绑定路径、允许目录和 JD，
模型不能传入其他文件、替换简历正文或提交自定义分数。工具 Schema 仍由 Registry 自动生成，
无需修改现有三个工具或 Agent Loop。语义调用拒绝嵌套工具请求，不构成第二个 Agent。

一条正常端到端流程：

1. Agent 将绑定任务的说明和 `match_resume_to_job` 描述交给模型。
2. 模型发起工具请求；Registry 执行匹配服务。
3. 服务通过原有 `read_resume` 读取授权目录中的简历，持有这份文本快照。
4. 调用同一个 Client，从 JD 语义提取职位、公司、必备和加分技能及待核实事项。
5. Python 去重后，将原始 JD 和简历快照交给模型，逐技能获取状态、引用和理由；不接受分数。
6. Python 验证引用、检查明显否定和基础学习标记、计算分数并生成 `EvidenceMatchReport`。
7. 报告作为原调用 ID 对应的 Tool Result 回到 Agent，模型再返回最终回复。

正常非空技能 JD 需要 **2 轮 Agent 调用 + 2 次工具内语义调用 = 4 次 API 请求**。
没有技能时跳过证据评估请求。所有调用共用同一个 DeepSeek Client 的请求预算，
模型重复调用匹配工具也会消耗该预算，没有隐藏的重试或额度重置。
工具内模型异常或非法 JSON/schema 会以脱敏异常交给 Executor，成为致命 `execution_error`；
文件错误仍保留 `access_denied` / `file_not_found` 策略，不会改路径重试。

### 报告和证据校验

`EvidenceMatchReport` 包含完整 `job`、简历来源和文本 SHA-256、每项技能的类别/状态/理由、
原文引用及行号、分数明细、综合分析和 `needs_verification`。综合分析由最终状态确定性生成，
不会保留模型在证据校验失败前作出的“全部满足”等自由总结。

| 状态 | 含义 | 计分系数 |
| --- | --- | --- |
| `supported` | 模型判断足以支持要求，且通过原文与保守规则检查 | 1 |
| `partial` | 仅满足部分要求或只有基础学习证据，且存在有效原文 | 0.5 |
| `not_found` | 当前简历未提供足够证据，不代表候选人没有能力 | 0 |
| `uncertain` | 判断缺失、引用无效、矛盾或信息不足，需进一步核实 | 0 |

模型只提交引用文本；来源、行号、上下文和 SHA-256 均由 Python 从授权简历快照生成，
不能由模型指定。引用必须是原文中逐字符相同的非空白片段，不做模糊匹配、大小写转换或省略号修复。
支持跨行引用并记录所有出现位置。报告中的来源相对于允许目录，行号从 1 开始；
SHA-256 标识读取后的 UTF-8 文本快照（不是文件字节校验和，读取可能规范化换行）。

无引用的 `supported/partial` 会降为 `uncertain`。不存在的引用被丢弃；同项技能只要出现无效引用，
正向判断就降为 `uncertain`，即使还有其他有效引用也不直接计分。缺失技能评估同样为 `uncertain`，
仍保留在评分分母；多余或重复的模型技能评估会拒绝整份输出。

引用所在段落会一并保留为上下文，避免截出“Python”掩盖“未使用 Python”。
复用 `find_evidence` 搜索同技能及已知别名的其他原文提及；明显否定/矛盾标记使正向匹配降为
`uncertain`。基础课程、beginner/tutorial 等标记使 `supported` 最多降为 `partial`。
这些规则刻意保守，只做有限的词法检查；原文定位通过不等于其语义相关性或内容真实性得到证明。

### 确定性评分

每项必备技能权重默认 **2**，加分技能权重默认 **1**，可通过
`EvidenceBasedMatcher(..., weights=ScoringWeights(required=3.0, preferred=1.0))` 调整。
这是每项技能的权重，不是固定的“必备 80%、加分 20%”分组比例。

```text
score = round(100 × Σ(技能权重 × 状态系数) / Σ(技能权重), 2)
```

例如：必备 Python=supported、SQL=partial，加分 Docker=not_found，
分数为 `100 × (2×1 + 2×0.5 + 1×0) / (2+2+1) = 60`。
`score_matches` 只接受 `SkillMatchState`，不接收 LLM 给出的数字；生产流程只把校验后的状态交给它。
分数限定在 0–100；无技能时返回 `score=0, applicable=false`，不是自动满分或候选人不合格。
分数明细的 `earned_weight/total_weight` 按实际出现的最大权重归一化，以避免极大权重溢出，
比值及最终分数不变。

技能按空白规范化、大小写及已有技能别名去重，同一技能同时出现在必备和加分项时只按必备计一次。
独立调用评分函数时，重复且一致的状态计一次，冲突状态保守按 `uncertain` 计分。
语义同义词主要由模型合并，Python 不推断任意两个不同名称是否等价。
学历、到岗时间、实习期限等非技能条件列入待核实信息，不混入该技能证据分数。

### 手动运行匹配 Demo

先安全导出 `DEEPSEEK_API_KEY`，从项目根目录执行：

```sh
.venv/bin/python -m examples.demo_matching_agent --run
```

默认使用 `examples/matching_resume.md` 和 `examples/matching_job.md`，内容均为虚构。
也可指定 `--resume examples/another.md --jd examples/another_job.txt`，两者必须在 `examples/` 内；
在构造 API Client 前就会检查输入，越界、缺失文件或指向目录外的符号链接会被拒绝。
`--model` 可以指定可用的非思考模型。

默认 Agent 上限 **3 轮**，共享预算 **6 次 API 请求**，单次最多输出 **2048 Token**，禁用 SDK 重试。
可选 `--max-steps 2/3/4`、`--max-calls 4/6/8`、`--max-tokens 1024/2048/4096`。
不带 `--run` 不会读取输入或构造 API Client。请求额度也包含失败请求；输入 Token 仍会计费，
这些限制不是精确的货币预算。

Demo 只有在 Agent 正常完成且真实执行过匹配工具后才展示报告，输出缩进的结构化 JSON。
展示的是工具的校验结果，**不采用助手最终文本中的报告或分数**；未执行工具、达到上限或异常时
返回非零退出码，不输出成功报告。报告会包含用户选择文件中的证据原文，属于任务产物，不应当作日志保存。
执行轨迹仍只保留脱敏元数据。

### LLM 与 Python 的职责边界及限制

LLM 负责 JD 语义提取、技能匹配程度提案、逐字引用选择和需核实事项建议。
Python 负责文件授权、Schema 验证、去重、原文定位与来源生成、保守状态降级、计分和权威报告构建。
LLM 不能通过 tool 参数更换输入、构造验证成功的来源字段、直接设分或覆盖报告。

现有局限：语义提取可能遗漏或误分类 JD 要求；真实存在的引用仍可能被模型误解，
不能证明候选人陈述属实。否定/基础学习检查可能因同段其他技能、历史时间变化或“not only”等表达误判，
也无法识别所有矛盾。非技能条件和经历真实性需人工核实；技能覆盖分不是录用概率。
输入中的提示注入无法仅靠提示语彻底消除，本地约束只保证有限的文件范围、引用定位和分数规则。
尚无语义结果缓存、大文件截断或 PDF/DOCX 支持。后续可加入人工标注评估集、别名与上下文规则改进，
以及对 JD 要求遗漏和引用相关性的独立评估，当前不扩展业务范围。

## Day 5：Cost-Aware Autonomous Evidence Gathering

Day 4 先生成不可覆盖的初步报告；Day 5 只对证据缺口补充取证。模型每轮必须返回一个
`GatheringDecision`，Python 严格验证以下三种行动及其字段，拒绝多余字段和模型自定分数：

| 行动 | 模型提供 | Python 行为 |
| --- | --- | --- |
| `SEARCH` | 目标技能、授权 source、简短理由 | 校验目标缺口和文件授权，通过 Registry 检索；有候选才调用模型重新评估 |
| `ASK_USER` | 目标技能、具体问题、简短理由 | 确认有有限恢复余量后返回 `waiting_for_user`，否则明确停止；不制造无法恢复的等待 |
| `FINISH` | 简短理由 | 返回 `finished`；允许因为低收益而保留缺口，不表示所有技能已经满足 |

模型决策上下文包含技能类别、原有权重、当前状态、授权文件大小及估算读取单位、已检索组合、
剩余检索次数、共享模型请求余量、上次工具结果和未经核实的用户回复。
读取单位为每 KiB 向上取整，是相对成本提示，不是价格或准确 Token 数。
Python 不强制“必备一定搜索、加分一定结束”，这些选择由模型给出理由；Python 只执行权限、
格式、目标技能和预算等硬约束。SEARCH/ASK_USER 不能针对未知技能或已经 supported 的技能。
决策输入另含 `available_searches`、`allowed_actions` 和逐次 `search_history`。
只有未检索、授权且配额足够的“技能/来源”组合才出现在可搜索列表中；没有组合时，响应 Schema
不再提供 SEARCH。授权文件列表只是背景信息，不代表仍可重复搜索。
失败反馈同时说明实际目标技能、来源、错误码和原因，避免只给出脱离上下文的 duplicate_search。
三种行动的参数契约同时体现在 JSON Schema 的 `oneOf` 与 Pydantic 校验中：
SEARCH 必填 skill/source，不能带 question；ASK_USER 必填 skill/question（至少 8 字符），
不能带 source；FINISH 不需要目标，skill/source/question 只能省略或为 null。
`ask_user_targets` 明确列出所有可询问的 partial/not_found/uncertain 技能；
检索过且仍 partial 的 SQL 依然可询问，不受 SEARCH 的去重和检索次数限制。
ASK_USER 必须使用报告中的技能名，不能省略目标或猜测映射。本版本仅支持技能澄清，
到岗时间等非技能条件不作为合法目标；这类信息继续保留为待核实项，不自动推断满足。
没有合法 SEARCH 时仅提供 ASK_USER（仍有恢复预算时）或 FINISH。

### 新接口及与现有 Agent 的集成

- `src/evidence_search.py`：`ProjectEvidenceSearch(authorized_sources, max_searches=3)`；
  `registry()` 显式注册 `search_project_evidence(skill, source)`。
- `src/autonomy.py`：`BudgetedLLMClient` 统一限制真实 Client 和 Mock 的请求尝试次数；
  `EvidenceGatheringSession.run()` 执行有限轮数的三行动循环，`resume()` 接收实际用户回复。
- `start_cost_aware_matching(...)`：先使用未修改的 Day 4 `Agent`、匹配工具和同一个预算 Client
  生成初步报告，再返回补充取证会话。不存在第二个框架 Agent 或后台任务。
- `schemas.py`：新增行动、候选证据、补充评估、变化记录、结果与脱敏轨迹模型。

`agent.py`、`matching.py`、DeepSeek 接口及旧工具保持不变。通用 Agent 不承担暂停语义，
Day 5 会话接管补充阶段的运行状态，避免把 ASK_USER 当作普通成功工具后继续循环。
报告中同时保留 `initial_report`、当前 `report`、每次评估的 `changes` 和 `trace`。

### 文件授权与检索

授权项必须是 `examples/` 内的具体 TXT/Markdown 文件，不接受目录或 glob。
相对授权路径以 `examples/` 为根；真实 Demo 默认没有补充文件权限，必须逐项 `--authorize`。
任意目录、越界路径、隐藏文件及 `.env` 均拒绝。检索参数只有技能和已经授权的 source ID，
没有可覆盖根目录的字段；模型即使在参数中构造路径也不能获得访问权限。

Python 检查真实路径、符号链接、实际扩展名及单文件 64 KiB 上限，并在读取前重新检查。
只读取被选择的文件，不扫描其他目录。检索使用现有字面关键词和已知别名规则，返回候选的
来源、行号、原文、段落上下文和文本 SHA-256，**不会将关键词命中直接判为 supported**。
搜索过的规范化“文件/技能”组合在同一会话中永久标记；无结果或读取失败也不允许重复检索。
大小写及已知技能别名不会创建新的检索配额，指向同一文件的授权别名会合并。
描述性技能名会按现有词表和词边界提取检索关键词，例如 `SQL查询`、`SQL 查询`、`SQL queries`
均用 SQL 及其别名召回候选，`Python开发` 等表达使用相同机制。不会把 MySQL/NoSQL 当作 SQL，
无法识别的技能仍按完整原词检索。检索去重和快照查询共用规范化关键词集合，换一种描述不能重复读取；
含多个已知技能的组合保留所有关键词。此规则也用于补充评估的否定检查，
但不修改 JD 技能名称、不合并评分要求，也不将较宽的关键词命中直接视为满足完整要求。

### 补充证据与重新评分

有候选结果时，模型仅评估目标技能，返回状态、`source/quote` 引用和理由。
Python 只接受原简历快照或**该技能实际检索过的授权文件快照**中的逐字引用；不会为了验证引用，
再去打开模型提到的新文件。未授权、未检索或虚构的来源/片段都不能获得正向分数。
存在无效引用时 supported/partial 降为 uncertain，其他已核实证据仍保留供查看。

复用 Day 4 的 `validate_quote`、技能别名和 `score_matches`；Day 5 的否定检查进一步限定到子句和目标技能。
Python 区分“没有 SQL 查询实践”和“没有部署到真实业务/生产环境”：前者是技能否定，后者只是环境限制。
SQL 实践原文不能仅因同段出现“没有部署”而被取消；若岗位还要求真实业务数据，则该子要求缺证时
按 partial，而不是自动 uncertain。已有经核验的 partial 不因仅涉及环境的限制降为零；这不产生新的技能能力。
纯实践要求不因无关的生产限制自动降级。模型提示也明确区分这两类判断，并要求引用限制条件。
针对技能本身的真实否定/矛盾仍可使分数下降，报告附上来源、行号及否定原文，便于核查。
只有基础学习证据时最多 partial；若同时有明确项目实践，则不会仅因为还引用了基础课程而一律降级。
不使用全局分数取最大值，也不承诺分数单调上升。
所有其他技能、JD 要求和原权重保持不变，分数仍严格由 supported=1、partial=0.5、
not_found/uncertain=0 的加权规则计算，模型不能直接设置数值。

为兼容 Day 4，每条引用仍复用 `ResumeEvidence`。其中 `source` 为实际文件来源，
历史字段 `resume_sha256` 在补充引用中表示**该来源文档**的文本快照摘要；报告顶层
`resume_sha256` 始终表示原始简历，不能把两者混淆。重复引用不重复计分。

### Human-in-the-Loop 与恢复

```python
from src.autonomy import start_cost_aware_matching

# client 可以是已有 DeepSeekLLMClient，也可以是 MockLLMClient。
session = start_cost_aware_matching(
    client, "examples/matching_resume.md", jd_text,
    authorized_sources=["projects/sql_project.md"], max_llm_requests=12,
)
result = session.run()
if result.status == "waiting_for_user":
    # 展示 result.question 和 result.context，等待实际用户回复。
    result = session.resume(actual_user_answer)
```

waiting 状态下再次 `run()` 不产生模型请求，也不假装完成。没有非空用户回答不能恢复；
非 waiting 状态不能调用 `resume()`。用户回复明确标为未经核实的线索，不加入文档证据库，
不能凭一句“我会 SQL”获得分数，回复中的文件路径也不自动授权。

如用户另外明确授权了文件，由应用单独传入
`session.resume(answer, additional_sources=["projects/another.md"])`。
该参数仍经过相同根目录和文件校验，与自然语言回答严格分开。
恢复沿用原会话的累计轮数、请求数、检索数、快照与重复记录，不退还已用配额。
首次有效回复获得一次性恢复窗口，默认最多 **2 轮新决策**，同时受原共享请求预算剩余量约束。
即使 ASK_USER 是初始阶段最后一轮，也有机会在该窗口内完成决策。
窗口只能使用一次，不会因反复提问或回复而重置；再次 ASK_USER 会明确停止，而非继续等待。
可通过 `resume_rounds=0/1/2` 配置 `EvidenceGatheringSession` 或 `start_cost_aware_matching`，
0 表示不允许进入需要恢复的等待状态。
会话目前只保存在内存，不能在进程退出后持久化恢复。

### 预算、状态与轨迹

默认初始自主阶段最多 **5 轮**，首次用户回复后最多 **2 轮恢复决策**，总计不超过 7 轮；
早于第 5 轮回复也只获得两轮恢复窗口，不累加未用初始轮数。最多 **3 次补充检索**（可设置 0–3），
完整流程共享 **12 次 LLM 请求尝试**，包含初步匹配、行动决策、补充评估及失败请求。
有候选的一次 SEARCH 需要一次额外模型评估，无候选跳过评估，节省请求。
SEARCH 在没有评估余量时不会读取文件；SDK 仍禁用自动重试。
调用预算不是精确货币上限，输入文本同样可能计费。

重复搜索或检索配额耗尽会反馈完整的目标/来源/原因，让模型在剩余轮数内改选 ASK_USER/FINISH；
连续两次忽略约束请求无效检索，以 `model_error/no_progress` 停止，不再消耗整段预算死循环，
也不由 Python 擅自伪造 FINISH。
行动 JSON/字段不合法或目标无效时，反馈 `invalid_action_arguments` / `invalid_target`
和合法目标列表，让模型在现有预算内纠正。整个会话最多给出两次纠正机会，用户恢复不重置；
第三次无效决策返回 `model_error/invalid_decision_limit`。每次纠正占用原有轮数和共享请求预算，
可提前因 `step_limit` / `budget_exhausted` 停止。模型请求异常仍直接终止；证据评估格式错误
也不会被当作可纠正的行动错误。反馈与轨迹不复制原始非法参数或异常内容。
权限错误立即以 `permission_denied` 停止，不尝试重构路径。
无结果不能无限重试。其他终止状态包括 `tool_error`、`model_error`、`budget_exhausted`、
`step_limit`，它们不等于 FINISH；已取得的进展仍保留在报告中。
等待仍消耗当前决策轮；没有任何共享请求余量或一次性窗口已用完时不进入 waiting。
若预算被其他调用在等待期间耗尽，恢复返回明确的 `budget_exhausted` 原因；
窗口用完则返回 `step_limit`。用户回复依然不能直接当作已验证文件证据。

脱敏 `trace` 仅包含轮次、行动、已知目标技能、检索成功与否、候选数量、错误码和状态。
不包含原始路径、引用全文、行动自由理由、用户回答、SDK 异常或密钥。
`report`、`initial_report` 和 pending 问题上下文是任务产物，可能含授权文本，不能当作日志整体记录。

### 离线和真实 Demo

```sh
.venv/bin/python -m examples.demo_autonomous_evidence
```

默认离线演示三个基本 Mock 场景及一次真实日志模式的可靠性复现，预设决策不代表真实自主推理；
检索、引用验证、评分和状态转换实际执行：

- A：必备 SQL 缺证，授权项目存在原文 → SEARCH → 核验后重新评分 → FINISH，0 → 100。
- B：必备 SQL 缺证且无授权材料 → ASK_USER → waiting_for_user；收到无文件佐证的回复后，
  FINISH 仍为 0 分，不用用户陈述冒充证据。
- C：仅缺低优先级加分项且无材料 → FINISH，不浪费检索和评估请求。
- D：SQL 实践与虚构数据/未部署说明混合，分数维持 70；一次重复 SEARCH 被拦截后 ASK_USER，
  在初始阶段最后一轮提问，收到实际回答后仍能进入有限恢复窗口并 FINISH，用户陈述不加分。
- E：真实本地工具依次 SEARCH SQL/Docker/PyTorch（候选 1/0/0）；Mock 故意使用非法的
  “到岗时间”目标，收到结构化错误后改为询问仍 partial 的 SQL，进入等待并在回复后有限恢复。

真实模式必须安全导出 `DEEPSEEK_API_KEY` 并由用户手动执行：

```sh
.venv/bin/python -m examples.demo_autonomous_evidence --deepseek --run --authorize projects/sql_project.md
```

可重复 `--authorize` 授予单个文件；不传时为无补充材料场景。`--model` 可指定可用的非思考模型。
支持 `--max-calls 8/12/16`、`--max-rounds 3/5/7`、`--max-searches 0/1/2/3`。
`--max-rounds` 限制初始阶段，恢复另有上述一次性两轮窗口，`--max-calls` 不因此增加。
单次模型最大输出 2048 Token，真实 Client 与跨阶段预算设置为相同请求上限。
需要在同一进程看到问题后输入一次实际回复时添加 `--interactive`；留空则保持等待。
也可通过 `--answer` 传入真实用户提供的回答，仅当出现 ASK_USER 时使用，两种方式互斥。
不带付费模式时不导入或构造 DeepSeek Client；`--deepseek` 缺少 `--run` 也不会发请求。
本次未运行真实付费 Demo。

当前局限：关键词检索可能遗漏语义改写；原文存在不等于相关性和内容真实性得到证明；
否定检查可能混淆历史时间变化或同段其他技能。材料授权依赖可信本地应用配置，
不提供抵御恶意并发文件替换的操作系统级原子隔离。读取成本只有粗略单位，没有金额估算或实时 Token 预算。
恢复不持久化，不能从 CLI 新进程接续旧会话。后续可改进成本估算和人工确认体验，
本次不开展 Day 6 评测或引入新的业务范围。

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
匹配测试覆盖原文定位、虚构引用、否定/矛盾、部分匹配、去重、权重、分数边界、空要求和非法输出，
并用共享 Mock 与 Fake SDK 验证完整 Agent + 语义调用流程、预算和 Demo。
测试中的 Demo 均注入 Fake SDK，不会启动真实付费请求。
Day 5 新测试覆盖三类行动、授权路径和符号链接、重复检索、虚构/否定证据、评分变化、等待与恢复、
共享模型预算、跨恢复轮数限制，以及初步 Agent 与自主阶段集成。离线 Demo 不需要 SDK 或 API Key。

## 设计限制

规则版 JD 提取只做文本匹配，词表外技能、否定、熟练度、隐含要求和复杂格式不作语义判断。
证据只是原文提及，不代表技能得到验证，例如“未使用 Python”仍会匹配。
文件工具只处理可信本地应用配置下的普通文本；路径检查和读取之间未实现操作系统级原子锁定，
不用于存在并发恶意符号链接替换的多租户文件系统。暂无文件大小限制或 PDF/DOCX 支持。
本阶段不包含前端或数据库；`completed` 仅代表模型返回最终回答，
不自动证明回答正确或用户目标已经实质达成。
DeepSeek 适配器目前仅支持同步、非流式、非思考的函数调用；不启用服务商 Beta strict 模式，
工具参数仍由本地 Pydantic 验证。不实现请求自动重试或整体货币预算；
既有 DeepSeek 真实调用已由用户验证，本次未执行 Day 5 的任何付费请求。

后续对接 Gemini 或 Ollama 时，实现满足 `LLMClient.complete()` 的适配器：
将中立消息和 `ToolSchema` 转换为供应商请求，将最终文本或一个/多个工具请求转换为
`LLMResponse`，解析参数 JSON，保留 ID，并正确回传含错误的 `ToolResult`。
若供应商缺少调用 ID，由适配器生成稳定且不重复的 ID 并维护映射。
适配器还需配置超时、供应商错误处理及凭据注入，并验证其支持的 JSON Schema 子集；
供应商异常不得携带密钥或完整请求进入日志。
