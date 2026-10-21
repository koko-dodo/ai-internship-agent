# AI Internship Agent

当前包含离线工具层、供应商无关的 LLM 接口、轻量 Agent Loop 和基于证据的岗位匹配。
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

## 设计限制

规则版 JD 提取只做文本匹配，词表外技能、否定、熟练度、隐含要求和复杂格式不作语义判断。
证据只是原文提及，不代表技能得到验证，例如“未使用 Python”仍会匹配。
文件工具只处理可信本地应用配置下的普通文本；路径检查和读取之间未实现操作系统级原子锁定，
不用于存在并发恶意符号链接替换的多租户文件系统。暂无文件大小限制或 PDF/DOCX 支持。
本阶段不包含前端或数据库；`completed` 仅代表模型返回最终回答，
不自动证明回答正确或用户目标已经实质达成。
DeepSeek 适配器目前仅支持同步、非流式、非思考的函数调用；不启用服务商 Beta strict 模式，
工具参数仍由本地 Pydantic 验证。不实现请求自动重试或整体货币预算；
单工具真实接入已由用户验证，本次未执行新的匹配流程真实调用。

后续对接 Gemini 或 Ollama 时，实现满足 `LLMClient.complete()` 的适配器：
将中立消息和 `ToolSchema` 转换为供应商请求，将最终文本或一个/多个工具请求转换为
`LLMResponse`，解析参数 JSON，保留 ID，并正确回传含错误的 `ToolResult`。
若供应商缺少调用 ID，由适配器生成稳定且不重复的 ID 并维护映射。
适配器还需配置超时、供应商错误处理及凭据注入，并验证其支持的 JSON Schema 子集；
供应商异常不得携带密钥或完整请求进入日志。
