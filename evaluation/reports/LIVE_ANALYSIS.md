# Day 6：真实案例 02 / 05 结果审计

本报告只分析已保存的 [案例 02](deepseek-case02-run01/real.json) 和 [案例 05](deepseek-case05-run01/real.json)。未重新调用模型，未调整标签、预测、指标或代码。以下准确率均保留原始报告口径；人工语义解释不替换正式结果。

## 1. 总览

两个实验均记录为 `mode=real`、`model=deepseek-flash`，使用冻结的 `gold-v1`：

`8b6061303cda37c88904cead19d77500f9e9ab6405ad7f993ffd1d3b7f46c105`

| 案例 | 方法 | 正确标签 / 指标分母 | Accuracy | 请求数 | 实际 total tokens | 延迟（秒） | 最终状态 |
|---|---|---:|---:|---:|---:|---:|---|
| 02 | Single | 0/1 | 0.0 | 1 | 587 | 4.042 | finished |
| 02 | Fixed | 1/1 | 1.0 | 3 | 2,125 | 6.773 | finished |
| 02 | Agent | 1/1 | 1.0 | 5 | 4,488 | 8.964 | finished |
| 05 | Single | 1/2 | 0.5 | 1 | 621 | 3.506 | finished |
| 05 | Fixed | 1/2 | 0.5 | 3 | 2,083 | 5.542 | finished |
| 05 | Agent | 0/3 | 0.0 | 7 | 7,266 | 12.699 | finished |

这些 tokens 来自报告中的 API usage，不是费用估计。案例 02 共 9 请求、7,200 tokens；案例 05 共 11 请求、9,970 tokens。两次实验合计 20 请求、17,170 tokens，但各自独立执行 25 请求上限，并非共用一个总预算。

主要结论：案例 02 中，两种有补充材料访问能力的方法均找到 RAG 证据；Agent 少查一个无关文件，但请求与 tokens 更多。案例 05 中，Agent 对查询实践与生产环境限制的实际判断基本合理，正式准确率下降主要受技能拆分、命名对齐和额外技能惩罚影响，同时存在一次无增量检索及成本较高的行动决策。两例不能支持“Agent 总体优于 Workflow”。

## 2. 准确率的实际定义

[metrics.py](../metrics.py) 使用 `canonical_skill(skill).casefold()` 对齐技能名称。记 Gold 技能键集合为 G、预测键集合为 P：

- 分子：Gold 中恰有一个对应预测、且状态完全相同的技能数。
- 分母：`|G| + |P − G|`，即 Gold 技能数加额外预测技能数。
- 缺失 Gold 技能仍占原有分母；额外预测技能各增加一个分母。
- `partial` 是四分类中的一个类别，命中 `partial` 得一个正确标签，不是半个正确标签。

[matching.py](../../src/matching.py) 的规范化采用已知完整别名，不会把任意包含 SQL 的长名称自动合并。因此本次 `SQL`、`SQL querying` 和生产环境条件是不同的指标键。准确率同时反映了技能抽取/命名和状态判断，不能当作单纯的状态语义正确率。

## 3. 案例 05：全部预测与 Gold 对齐

### 3.1 冻结口径与原文

JD：

> Required: SQL.
> SQL querying must include experience with real business data in production.

Gold 只有一个复合要求：`SQL = partial`。完整授权材料足以支持部分满足，但不足以支持真实业务数据、生产环境经验：

| 来源与行号 | 原文 | Gold 关系及含义 |
|---|---|---|
| `evaluation/05/resume.md:3` | I completed a basic SQL tutorial. | `partial`：基础学习证据 |
| `evaluation/05/sql.md:1` | I wrote SQL JOIN and GROUP BY queries and checked the returned rows. | `partial`：本人具体查询实践，但未满足全部 JD 条件 |
| `evaluation/05/sql.md:3` | The project used synthetic data and was not deployed to production. | `limits`：限制真实业务/生产环境条件，不否定已经完成的查询实践 |

这里的来源路径相对 examples 授权根目录；物理文件位于 `examples/evaluation/05/`。Gold 评估的是完整授权文件是否支持要求，不是验证候选人的真实能力。

### 3.2 每一项预测

| 方法 | 原始预测技能名 | 状态 | 当前指标如何处理 |
|---|---|---|---|
| Single | `SQL` | partial | 命中 Gold，正确 |
| Single | `Experience with real business data in production` | not_found | 额外技能 |
| Fixed | `SQL` | partial | 命中 Gold，正确 |
| Fixed | `SQL querying on real business data in production` | not_found | 额外技能 |
| Agent | `SQL querying` | partial | 额外技能；未映射至 Gold SQL |
| Agent | `real business data in production` | not_found | 额外技能 |

所以：

- Single：一个 Gold 正确，一个额外技能，`1 / (1 + 1) = 0.5`。
- Fixed：一个 Gold 正确，一个额外技能，`1 / (1 + 1) = 0.5`。
- Agent：缺少名为 SQL 的预测，两个额外技能，`0 / (1 + 2) = 0.0`。

Agent 没有把查询实践改判为 uncertain 或 not_found；它最终输出的是 **`SQL querying = partial`**。补充评估明确接受 JOIN/GROUP BY 实践，同时指出 synthetic data / not deployed 不满足生产条件。这与 Gold 对复合要求的实质判断接近，不能用正式 0.0 推断“Agent 不承认 SQL 实践”。

### 3.3 原因归类

1. **语义抽取/表示问题**：Single、Fixed、Agent 均把同一 SQL 要求的生产条件拆成额外预测技能；Agent 还将主技能改名为 SQL querying。Fixed 与 Agent 的初始抽取已经不同。
2. **指标影响**：精确别名对齐及额外技能惩罚使 Single / Fixed 为 0.5，Agent 为 0；Agent 的语义等价主技能未命中 Gold。不能事后修改别名或删除额外项来修饰本次结果。
3. **检索问题**：SQL 正向实践已被成功检索，不是漏掉 SQL 证据导致最终差异。第二次按生产条件长短语检索没有命中，是字面检索及目标表示的局限。
4. **决策效率问题**：Agent 对同一已读文件再次检索另一个目标，没有新增候选；随后询问用户也未获得可授权文件。这些增加成本，但不是正式 0.0 的直接计算原因。

Single 的原始模型分数为 20；Fixed / Agent 的确定性分数均为 25，补充前后不变。后者各有两个同权重必备项，一个 partial、一个 not_found；不能把 25 当作准确率，也不能与 Single 自行给的 20 当作同一评分器比较。把子条件抽成独立要求也会影响确定性评分分母。

## 4. 检索材料、候选和有效引用

### 4.1 实际工具轨迹

| 案例 | 方法 | 目标与授权文件，按执行顺序 | 候选数 | 报告 Useful Retrieval |
|---|---|---|---|---|
| 02 | Fixed | RAG → `evaluation/02/a_notes.md`；RAG → `evaluation/02/b_rag.md` | 0；1 | 1/2 |
| 02 | Agent | RAG → `evaluation/02/b_rag.md` | 1 | 1/1 |
| 05 | Fixed | SQL → `evaluation/05/sql.md` | 1 | 1/1 |
| 05 | Agent | SQL querying → `evaluation/05/sql.md`；real business data in production → 同文件 | 1；0 | 0/2，存在名称对齐影响 |

Single 没有外部检索权限和工具调用，两例均只使用 Resume 与 JD。

案例 02 的 a_notes 只有虚构团队日程，没有 RAG 实践。b_rag 的候选命中第 1 行，候选上下文覆盖完整三行：

> Retrieval: I implemented RAG retrieval with document citations and tested retrieval against a fixed set of questions.
> Augmentation: I inserted the retrieved passages into the LLM prompt as context.
> Generation: I called the LLM with that context to produce answers with citations to the retrieved documents.

这同时包含 Retrieval、Augmentation、Generation，而不是仅凭 RAG 关键词判断 supported。

案例 05 的首个候选均是 sql.md 第 1 行的查询实践。候选 context 只含该段；第 3 行被空行隔开。补充评估还使用授权文件快照，最终确实引用了第 3 行限制句，所以不能从候选 context 推断模型完全没看见限制条件。

检索归一化与指标规范化不同：SQL、SQL querying、SQL querying on real business data in production 在检索端共享 SQL 键；Fixed 不会再以同一组合重复查文件。Agent 的 `real business data in production` 不含 SQL，属于另一合法键；工具用完整短语检索，原文没有该连续字符串，因此返回 0。它不是 duplicate_search，也不是权限拒绝，但在已经掌握 synthetic / no production 事实后没有增量价值。

### 4.2 “有效证据数”的不同层次

候选数、最终引用条目数、唯一引文数和语义支持数不能混用。以下“原文有效”只指授权文件中可定位的真实引用；不保证支持技能。

| 案例 | 方法 | 最终原文有效引用 / 全部引用 | 唯一引文数¹ | 自动 Gold 关系匹配 |
|---|---|---:|---:|---|
| 02 | Single | 1/1 | 1 | unreviewed × 1 |
| 02 | Fixed | 3/3 | 3 | unreviewed × 3 |
| 02 | Agent | 4/4 | 4 | unreviewed × 4 |
| 05 | Single | 1/1 | 1 | partial × 1 |
| 05 | Fixed | 6/6 | 5 | partial × 2、limits × 1、unreviewed × 3 |
| 05 | Agent | 5/5 | 5 | unreviewed × 5 |

¹ 按来源、原文、起止行去重；同一句的子片段仍是不同引文，不能当作独立事实。

**案例 02 的语义标注覆盖局限**：Gold 将 RAG 三行合在一个 supports 引文中；实际模型拆行引用。当前关系匹配要求某个完整 Gold 引文包含在单个预测引文中，不跨多个引用合并验证。因此 Fixed 的 Retrieval / Generation 引文和 Agent 的三行分拆引文均未自动命中 supports。Fixed 的补充说明讨论了 Augmentation，但最终未单独引用该行；Agent 引用了全部三行。两者还保留了 Resume 中 text formatting utility 的引用，它存在于原文但不构成 RAG 支持。自动语义支持率均为 unavailable，而非“0% 语义正确”或“证据不存在”。

**案例 05 的引用细节**：Fixed 的 SQL 引用为 tutorial、完整查询实践、完整限制句，以及限制句的两个子片段 `The project used synthetic data` / `was not deployed to production`。子片段来自 Python 限制条件保护逻辑；它们是真实限制，不能独立当作正向实践。额外的复合技能还重复引用一次 tutorial，故总条目为 6、唯一引文 5。自动语义覆盖为 3/6；已审阅的正向预测引用中，2/3 有 partial 正向关系，另 1 条只有 limits。

Agent 的五条引用与 Fixed 主技能的五条相同，但均挂在 `SQL querying` 下，自动指标找不到 SQL Gold，所以全为 unreviewed。人工按内容可以识别 tutorial / 查询实践的部分支持、生产句及其片段的限制作用；这只是审计解释，不回写正式标签或指标。

同理，Agent 的第一次 SQL 检索实际获得了新增、可信的查询实践；但 Useful Retrieval 按目标技能键查 Gold，SQL querying 没有对齐，正式仍为 0/2。不能据此声称两次都没有有用材料。第二次确实没有新增候选。Fixed 的 1/1 则来自新增 Gold 证据，不是状态改变：SQL 补充前后都是 partial。

## 5. 案例 05：Agent 七次请求逐项解释

| 请求 | 阶段 | 结果或用途 | Prompt tokens | Completion tokens | Total |
|---:|---|---|---:|---:|---:|
| 1 | JD extraction | 拆成 SQL querying 与生产条件两个要求 | 332 | 51 | 383 |
| 2 | Initial assessment | partial / not_found | 497 | 132 | 629 |
| 3 | Action decision | SEARCH SQL querying；随后工具返回 1 个候选 | 1,136 | 68 | 1,204 |
| 4 | Supplemental assessment | 接受查询实践，保留生产条件不足；仍为 partial / not_found | 908 | 227 | 1,135 |
| 5 | Action decision | SEARCH 生产条件；随后工具返回 0 个候选 | 1,204 | 73 | 1,277 |
| 6 | Action decision | ASK_USER SQL querying，进入 waiting_for_user | 1,229 | 108 | 1,337 |
| 7 | Action decision | 收到预设回复后 FINISH | 1,236 | 65 | 1,301 |
| 合计 | | | 6,542 | 724 | 7,266 |

本地搜索、Python 校验/评分、交付模拟回复本身不另占 LLM 请求。四次行动决策共 5,119 tokens，约占 70.5%；三次语义处理共 2,147 tokens。Fixed 的三次语义请求共 2,083 tokens，行动由 Python 固定规则选择。因此 Agent 比 Fixed 多 4 请求、5,183 tokens，其中 5,119 是行动决策，余下 64 来自独立语义调用的差异。

行动轨迹是：第 1 轮 SEARCH + 重评 → 第 2 轮 SEARCH 空结果 → 第 3 轮 ASK_USER → waiting → 用户回复 → 第 4 轮 FINISH。没有 duplicate_search、invalid_target、非法参数或 API 错误；invalid_actions 与 duplicate_actions 都是 0。

Agent 提问原文：

> 请说明你在实际工作或项目中用 SQL 做过哪些查询与分析（例如数据量、复杂 join/聚合、性能优化），并提供可佐证的项目或成果细节。

问题较宽，重复询问已经有实践证据的 SQL，并引入 JD 没明示的性能优化。更有针对性的方向应是缺失的真实业务/生产经验及新增可授权材料。不过，关键条件确实未满足，询问本身合法，不能因事后知道预设回复而认定必然不该询问。Fixed 也询问了一次，但问题是固定的 `Can you provide candidate-owned SQL project evidence?`，同样不够聚焦。

两者收到完全相同的案例预设回复：

> I have no real business project document to authorize.

回复均记录为 `verified=false`，没有转成文件证据、增加授权、提高状态或分数。Agent 最后一轮理由提及“不支持的询问方式限制”，但轨迹没有 ASK_USER 被校验拒绝的事件；不能将模型理由当作实际 invalid_target 记录。恢复窗口不再允许再次等待，与已发生错误是两回事。

## 6. 案例 02：信息收益与决策成本

Gold 是 RAG supported。Single 输出 RAG not_found，无额外技能，因此 0/1。它只能看到 text formatting utility 简历，没有 RAG 补充材料；这个输出符合其受限输入，不能据此诊断幻觉或 RAG 推理能力差。完整信息 Gold 与弱信息 baseline 的差距包含资料可见性收益。

Fixed 和 Agent 均从 not_found 变为 supported，确定性分数 0 → 100，均为 1/1。Fixed 按顺序查 a_notes 再查 b_rag；Agent 直接选择 b_rag。

| 方法 | 请求阶段及每次 total tokens |
|---|---|
| Fixed | JD 354；初评 569；补充评估 1,202 |
| Agent | JD 354；初评 549；SEARCH 决策 1,181；补充评估 1,235；FINISH 决策 1,169 |

Agent 避免了一次空检索，但比 Fixed 多 2 请求、2,363 tokens，延迟也更长，没有准确率增益。这是局部检索选择更省与整体 LLM 成本更高同时存在的实例。

## 7. Gold、授权、预算与可比性核查

| 项目 | 已保存记录与本地复核结果 |
|---|---|
| Gold | 两份报告均为 gold-v1、相同冻结 fingerprint；当前冻结清单验证通过。没有因预测调整标签 |
| 同案例输入 | 报告的 same_inputs_grants_budgets 均为 true；Single 依协议没有补充材料，Fixed / Agent 授权列表相同 |
| 02 授权 | Fixed / Agent 均可用 a_notes.md、b_rag.md；实际搜索均在列表内 |
| 05 授权 | Fixed / Agent 均仅可用 sql.md；所有搜索均来自该文件 |
| 引文 | 六个运行的所有已输出引文均可在各自可见授权文件中定位；Single 在方法内未验证，报告后置审计不改变该性质 |
| 执行顺序 | 每例均 Single → Fixed → Agent |
| 请求上限 | Single 1，Fixed 12，Agent 12；单次实验共享上限 25；实际 02 为 1/3/5，05 为 1/3/7 |
| 搜索/轮数 | Fixed / Agent 最多 3 次搜索、初始最多 5 轮、一次性恢复 2 轮；实际搜索 02 为 2/1，05 为 1/2，均未超限 |
| 用户交互 | 02 无交互；05 两者均一次等待、一次相同预设回复、一次恢复后结束；未编造用户回答 |
| 错误与预算 | 所有模型请求 error_code 均为空；没有失败请求；SDK retries=0。本次不能实证“失败如何计数”，因为没有失败样本 |
| 用量 | 每个请求均有 usage；api_requests、llm_requests、model_outputs 条数相等，逐请求 tokens 加总与报告总量一致 |
| 最终状态 | 六个运行均 finished；05 Fixed / Agent 的中间 waiting_for_user 已恢复，不是最终未完成 |
| 故障注入 | 两例均无 injected_fault；未启用额外 normal-access 对照，无需混合故障与正常访问结果 |

“遵守 Gold”不意味着方法必须输出 Gold 结果：Gold 用于观察性比较，不能注入决策或强制修正模型。Single 保留模型原始分数与未验证引用，Fixed / Agent 保留验证后状态与确定性评分。

案例 02 的 policy_ablation 记录 same_initial_states=true、same_initial_checkpoint=true。案例 05 两项均为 false，虽然数据、授权和预算一致，但抽取和初评并不相同。因此案例 05 不是“只改变行动策略”的干净消融，不能把差异全部归因于 SEARCH / ASK_USER / FINISH。

审计证据边界：这些核查支持保存记录内部一致、当前冻结数据一致以及已报告访问/引文合法；报告不是完整 HTTP 请求或文件系统访问日志，不能独立证明历史服务端实际收到的所有内容、当时所有代码版本或未记录的行为。

## 8. 结论分层与后续建议

### 方法自身问题

- JD 要求和子条件拆分不稳定，Agent 的主技能命名漂移；这是抽取/输出表示问题。
- 05 Agent 对生产条件重复读已知文件，返回空候选；合法但无增量收益。
- 05 两种方法的提问都可以更聚焦缺失条件。Agent 行动决策开销明显，当前没有抵消这些开销的准确率收益。
- 本次没有证据表明 Agent 将“未部署”误判为“不会 SQL”；其补充语义评估保留了 partial。

### 数据集口径与指标影响

- Gold 用一个技能承载全部 JD 明示条件；模型拆成多个技能造成额外项。SQL partial 的既定口径有查询实践与生产限制共同支撑，无需根据本次结果改标签。
- 精确名称对齐使 Agent 的主技能状态虽合理却未命中 Gold，并同时影响 Useful Retrieval 和语义关系覆盖。
- RAG 的 Gold 引文合并、实际引用拆行，导致语义审阅覆盖为 0；不是判定证据不支持 RAG。
- 原文存在率为 100% 不等于正向语义支持率为 100%；限制句、无关引用和重复片段必须分开理解。

### 后续改进建议（本次不实施）

1. 在下一版实验协议中预先定义稳定技能 ID、技能与条件的结构，分开报告抽取/额外技能错误与已对齐状态准确率；使用通用且有边界的名称映射，不为个案事后特判。
2. 对跨引文证据覆盖、完整句与限制片段关系制定一致标注规则，区分未审阅与错误；若修改 Gold 或指标，另做版本并保留当前结果。
3. 在未来策略消融中固定并共享初始语义检查点，再比较行动策略；仍保留端到端独立调用结果，避免掩盖抽取不稳定性。
4. 让行动考虑已读文件及已知限制，减少无增量重查；询问集中于尚缺的条件与可授权新证据。是否值得增加决策调用应由成本/质量结果检验。
5. 扩充场景、重复独立运行、控制或随机化顺序，报告离散程度，再讨论稳定收益；不得用本次两例宣称总体优势。

## 9. 局限性与面试中可如实表述的结论

只有两个虚构案例，每方法各运行一次；使用供应商默认采样、无 seed，方法按固定顺序执行。gold-v1 来源是辅助起草后按用户独立语义复核决定冻结，不声称多人一致性。没有统计显著性或总体泛化结论。实际 token 数可比较调用量，但没有价格、缓存计费等完整信息，不能据此报真实金额。此审计没有重跑 pytest、离线评测或真实 API，因为没有修改实现，任务仅为分析现有结果。

可如实说明：

> 我用同一个模型比较了 Single、固定工作流和自主 Agent。在一个缺少简历 RAG 证据的案例中，两种带检索的方法都达到了 Gold；Agent 少查一个文件，但多用了两次模型请求。在另一个带生产环境条件的 SQL 案例中，Agent 保留了 partial 判断，但技能拆分和名称对齐使正式准确率为零，还出现了一次没有新增证据的搜索。实验说明自主决策可以改变检索选择，但不保证比固定流程准确或便宜；目前需要先改善评测对齐、控制消融变量，再扩大实验。
