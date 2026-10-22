# Gold Label Audit — 人工复核准备稿

## 复核范围与状态

本稿只整理 `day6-v1` 的现有标注与待确认问题，不批准或替换任何 Gold Label。
已逐一阅读 [cases.json](cases.json)、[GOLD_NOTES.md](GOLD_NOTES.md)，以及其中引用的全部
33 个原文文件：12 份 JD、12 份 Resume、9 份明确授权的补充材料。
当前标签由编码助手在开发阶段拟定，**尚未经独立人工复核**。下文“当前依据”解释的是现有标注，
不表示复核人已经认可。未用 Mock 输出决定任何标签，也未读取 Mock 脚本来推导标注。

来源定位采用“文件名:行号”，路径均相对于 `examples/`；文中的链接直接指向案例文件。
英文引文保留原文。已机械核对现有 12 条标注引用，原文与 `start_line/end_line` 完整行范围一致；
这只验证定位，不验证语义支持、候选人能力或文件陈述在现实中的真实性。

本次阅读时的文件 SHA-256，用于人工复核时确认版本：

```text
cases.json      28524c4bd93f9a33c9ae1d2d5cd3dfb5b66c52d7533b9e33b543fa30ae74333c
GOLD_NOTES.md   9a70f61ac85786fa5b6f21e756205f49f94c8e995bfefcf8ab69123f78af80c9
```

## 为什么是 12 个案例、13 个技能标签

计数单位是 **案例 × Gold 技能**，而不是案例、关键词、引用或具体子条件。
案例 01 有 Python、SQL 两项，其余 11 个案例各一项：`2 + 11 × 1 = 13`。

| 统计维度 | 当前数量 |
| --- | --- |
| 技能类别 | Python 2；SQL 7；RAG 3；Docker 1 |
| 状态 | supported 6；partial 1；not_found 5；uncertain 1 |
| 必备/加分 | required 13；preferred 0 |

依据现有 [metrics.py](metrics.py) 的实现，对每个案例先做技能名称规范化，定义：

```text
G = Gold 中的不同技能名集合
P = 方法输出中的不同技能名集合
该案例分母 D = |G| + |P - G|
该案例分子 C = Gold 技能中“仅有一个对应预测且状态与 Gold 相同”的数量
全量准确率 = ΣC / ΣD
```

因此每种方法在全量 12 个案例、没有额外预测技能时，分母为 **13**；不是三种方法合并为一个分母。
额外预测的未知技能会增加该方法的分母，所以 13 是当前 Gold 总数，不是任何输出下都固定的分母。
漏掉 Gold 技能不会减少分母；重复预测某个 Gold 技能会使该项不能计对，不会新增一个 Gold 标签。
同名未知技能重复出现按其规范化后的不同名称计额外项，重复项另外统计。

以下内容不另加技能标签：

- 案例 05 的“会 SQL 查询”及“真实业务数据/生产环境经验”，目前合在一个 SQL 要求中。
- 同一技能的多条引用、JOIN/GROUP BY 等实践细节，不各算一项技能。
- `not_found` 即使证据列表为空，仍是参与分类的一项 Gold。
- waiting、权限失败和工具失败不会使该案例的技能标签被剔除；有预测则比较预测，缺项计错。
- 用户回答、检索次数、评分权重、得分变化不作为技能准确率分母。

人工需确认：这种复合技能粒度与微平均是否适合研究问题；当前没有任何 preferred 标签，
不能据此评价“仅缺低优先级加分项时是否值得检索”。本稿只记录这些边界，不扩展数据集或修改指标。

## 标签依赖与交互一览

“依赖补充材料”包括必须检查材料才能确认缺证或限制，不能只理解为正向证据。
用户回复仅是允许使用的模拟陈述，只有系统实际提问后才交付；不是已验证文件证据。

| 案例 | 当前 Gold | 标签依赖 | 用户交互/运行条件 |
| --- | --- | --- | --- |
| 01 | Python supported；SQL supported | 简历足以支持；补充 notes 无关 | 未配置回复 |
| 02 | RAG supported | 依赖 b_rag.md；a_notes.md 为无关材料 | 未配置回复 |
| 03 | SQL not_found | 简历与授权 notes 均无相关证据 | 配置“没有更多可授权文件”的回复 |
| 04 | SQL uncertain | 简历学习线索 + 补充材料的实践否定 | 配置“无法提供查询归属证据”的回复 |
| 05 | SQL partial | 简历 + 补充实践及生产环境限制 | 配置“没有真实业务文件”的回复 |
| 06 | Docker not_found | 仅简历上下文；无授权补充文件 | 未配置回复 |
| 07 | RAG not_found | 仅简历，且无授权补充文件 | 等待用户场景；未配置回复 |
| 08 | SQL not_found | 简历缺证；口头声明不补足文件证据 | 配置未核实的 SQL 经历声明 |
| 09 | Python not_found | 仅实际简历；模型行为不是标签依据 | 未配置回复；若提问则没有预设答案 |
| 10 | RAG supported | 依赖授权 rag.md 的完整事实 | 注入 access_denied；未配置回复 |
| 11 | SQL supported | 依赖授权 sql.md 的完整事实 | 注入 io_error；未配置回复 |
| 12 | SQL supported | 依赖授权 sql.md | 非法行动为行为测试；未配置回复 |

## 案例 01 — complete

**JD 要求及条件。** [jd.md:2](../examples/evaluation/01/jd.md) 原文：

> Required: Python, SQL.

职位为 Data Intern；未写熟练度、年限、生产部署、业务数据或必须实现哪些 SQL 功能。
“基础 Python”“查询要求”是当前解释采用的满足门槛，不是 JD 中另外明示的条件。

**Resume 相关原文。** [resume.md:3、5](../examples/evaluation/01/resume.md)：

> I implemented Python CSV validation with unit tests.
>
> I wrote SQL JOIN queries and checked aggregates against expected rows.

**授权补充原文。** [notes.md:1](../examples/evaluation/01/notes.md)：

> Fictional project meeting agenda.

该补充材料没有 Python/SQL 实践信息。

**当前 Gold 及依据。** Python `supported`，引用行 3，关系为 `supports`；SQL `supported`，
引用行 5，关系为 `supports`。当前依据是第一人称实现、测试和结果校验足以支持未进一步限定的技能要求，
正向结论不依赖补充材料。

**歧义。** JD 只有技能名，无法单独确定“完全满足”的深度。文档自述也不是实际代码、测试报告或能力测验。

**建议人工重点检查。** 是否认可“具体、本人执行的单个实践描述”足以满足这种宽泛 JD？
是否应统一把纯文档陈述当作案例内证据，而不要求实际代码？这一门槛需同样用于案例 02、10、11、12。

人工结论：**待复核**。

## 案例 02 — supplement_available

**JD 要求及条件。** [jd.md:2](../examples/evaluation/02/jd.md)：

> Required: RAG.

职位为 Retrieval Intern；没有明确要求生成环节、具体检索方案、效果阈值或部署环境。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/02/resume.md)：

> Fictional candidate Birch. I built a text formatting utility.

这句话没有交代 RAG 实践。

**授权补充原文。** [a_notes.md:1](../examples/evaluation/02/a_notes.md)：

> Fictional team schedule and meeting agenda.

[b_rag.md:1](../examples/evaluation/02/b_rag.md)：

> I implemented RAG retrieval with document citations and tested retrieval against a fixed set of questions.

**当前 Gold 及依据。** RAG `supported`，仅 b_rag.md 的完整句子被标为 `supports`。
当前依据为本人实现检索、提供文档引用、使用固定问题测试；a_notes.md 不提供技能证据。
此标签依赖补充材料，不能从原简历独立推出。

**歧义。** 文本明确写了 “RAG retrieval”，但未描述检索内容如何进入 LLM 上下文、如何生成回答，
也没有测试结果或质量指标。检索与引用不必然等于完成整个检索增强生成链路。

**建议人工重点检查。** JD 的 RAG 是否只要求检索侧实践，还是需要完整 retrieval + augmentation + generation？
自述中的 RAG 命名是否足以弥补技术细节缺失？需与案例 10 采用同一门槛。

人工结论：**待复核，优先确认 RAG 满足标准**。

## 案例 03 — empty_retrieval

**JD 要求及条件。** [jd.md:2](../examples/evaluation/03/jd.md)：

> Required: SQL.

没有额外熟练度或环境要求。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/03/resume.md)：

> Fictional candidate Cedar. I wrote an article about teamwork.

**授权补充原文。** [notes.md:1](../examples/evaluation/03/notes.md)：

> I organized a fictional meeting and wrote the agenda.

两处均没有 SQL 查询、学习或实践信息。

**当前 Gold 及依据。** SQL `not_found`，标注引用为空。完整授权输入没有足够 SQL 证据；
不是“此人不会 SQL”。结论依据简历与补充材料的共同缺证，而非只查简历。

**用户回复。** cases.json 配置的未经核实陈述为：

> I have no additional SQL project files to authorize.

回复仅说明当前没有更多可授权文件，既不否定 SQL 能力，也不补充已验证证据。

**歧义。** 缺证后的 ASK_USER/FINISH 属于行动选择问题；当前技能 Gold 没有标注一个唯一正确行动。

**建议人工重点检查。** 是否认同纯缺证统一为 `not_found`，而不是 `uncertain`？
是否明确把“缺证”“没有更多文件”和“没有能力”分开？

人工结论：**待复核**。

## 案例 04 — negation

**JD 要求及条件。** [jd.md:2](../examples/evaluation/04/jd.md)：

> Required: SQL.

JD 未明示必须本人编写查询；当前标注把查询实践归属作为重要满足条件。

**Resume 与授权补充的正向线索/否定对照。**

| 来源 | 原文 | 当前标注关系 | 能说明什么 |
| --- | --- | --- | --- |
| [resume.md:3](../examples/evaluation/04/resume.md) | I completed a basic SQL tutorial. | partial | 有基础学习，不直接声称写过查询 |
| [sql.md:1](../examples/evaluation/04/sql.md) | I have never written SQL queries; the teammate authored all queries in the project. | contradicts | 明确否定本人写查询，并把该项目查询归于队友 |

**当前 Gold 及依据。** SQL `uncertain`。现有解释强调基础学习与本人查询实践否定，需要核实工作归属，
不能把项目 SQL 算到候选人头上。此标签结合两份文件，而非单凭简历。

**用户回复。** 未经核实陈述：

> I cannot provide evidence of query ownership.

不能提供归属证据不等于再次证明没有查询能力。

**歧义。** “完成教程”与“没写过查询”可以同时为真，未必存在逻辑矛盾；也可能教程包含查询，
但原文没有说明。补充句的 `never` 看似覆盖全部经历，后半句则聚焦该项目。
`contradicts` 究竟是在否定“本人实践已满足”的推断，还是与简历中某个明确主张冲突，需要界定。

**建议人工重点检查。** 对这种“基础学习成立、实操被否定”的情形，应依现有定义选 `uncertain`，
还是 `partial`/`not_found` 更准确？显式否定是否一律要求 uncertain？
必须与案例 06 的归属不足处理对照，避免仅因出现否定词而机械分到某状态。

人工结论：**待复核，优先确认状态与 contradicts 的适用边界**。

## 案例 05 — partial_requirement

**JD 要求及具体条件。** [jd.md:2–3](../examples/evaluation/05/jd.md)：

> Required: SQL.
> SQL querying must include experience with real business data in production.

除 SQL 查询外，明确要求真实业务数据及生产环境经验。这些子条件目前合并在一个 SQL Gold 中。

**Resume 与授权补充的正向实践/限制对照。**

| 来源 | 原文 | 当前标注关系 | 作用范围 |
| --- | --- | --- | --- |
| [resume.md:3](../examples/evaluation/05/resume.md) | I completed a basic SQL tutorial. | partial | 基础学习线索 |
| [sql.md:1](../examples/evaluation/05/sql.md) | I wrote SQL JOIN and GROUP BY queries and checked the returned rows. | partial | 本人查询实践成立，但独立不足以证明全部 JD 条件 |
| [sql.md:3](../examples/evaluation/05/sql.md) | The project used synthetic data and was not deployed to production. | partial | 对这个项目的数据及部署环境作限制，不否定 SQL 查询实践 |

**当前 Gold 及依据。** SQL `partial`：具体查询实践有支持，而真实业务/生产环境子要求没有被满足或证明。
不能因未上线就把查询实践本身当成虚构，也不能因做过查询就把环境条件当成满足。
补充材料对该解释是关键。

**用户回复。** 未经核实陈述：

> I have no real business project document to authorize.

这表示没有可授权文件，并不证明候选人在所有经历中都没有真实业务经验。

**歧义。** 限制句只描述当前项目；不能外推到候选人的完整经历。
此外，三条引用目前均使用 `relation=partial`，但生产限制句本身不是技能实践的正向证据。
现有 Metrics 对 partial 判断允许 partial 关系作为正向引用支持，人工需确认该关系是否意在表达
“该句帮助解释为什么仅部分满足”，而不是“该句单独足以支持具有部分技能”。本次不修改关系或指标。

**建议人工重点检查。** 是否认可一个 SQL 复合标签表示所有子条件？
生产限制的关系应如何解释，是否必须与实践句联合阅读？项目层面的限制与候选人整体能力是否被严格区分？

人工结论：**待复核，优先确认复合要求与限制句关系语义**。

## 案例 06 — irrelevant_keyword

**JD 要求及条件。** [jd.md:2](../examples/evaluation/06/jd.md)：

> Required: Docker.

JD 没有具体说明容器构建、运行、部署、文档知识或熟练程度。

**Resume 的关键词线索/归属限制对照。** [resume.md:3](../examples/evaluation/06/resume.md)：

| 句子部分 | 原文 | 应区分的含义 |
| --- | --- | --- |
| 团队层面 | The team used Docker; | 技术出现在团队项目，不证明候选人本人执行 |
| 候选人层面 | I only wrote documentation. | 自述职责仅为文档，不提供容器操作实践 |

完整标注原文为：

> The team used Docker; I only wrote documentation.

**授权补充材料。** 无；不得推断存在未授权项目文件。

**当前 Gold 及依据。** Docker `not_found`；完整句子关系标为 `irrelevant`。
现有依据是团队关键词加文档职责不足以证明个人 Docker 实践；该句确实存在，但不能直接当成能力支持。
此判断仅依据简历。

**歧义。** 写文档可能需要一定 Docker 理解，却不等于操作实践；JD 又没有明确要求 hands-on。
这条原文与归属判断实际相关，`irrelevant` 可能更准确地理解为“不提供所需正向支持”，而非“完全无关”。
“仅写文档”的排他性与案例 04 的实践否定应采用一致的分类原则。

**建议人工重点检查。** Docker 的最低满足门槛是什么？这里应为 not_found 还是 partial/uncertain？
`irrelevant` 是否应涵盖“相关但不能支持正向技能结论”的文本？

人工结论：**待复核，优先确认个人归属、状态及关系标签边界**。

## 案例 07 — waiting_user

**JD 要求及条件。** [jd.md:2](../examples/evaluation/07/jd.md)：

> Required: RAG.

未增加技术实现或熟练度条件。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/07/resume.md)：

> Fictional candidate Gale. I edited a newsletter.

**授权补充材料。** 无。

**当前 Gold 及依据。** RAG `not_found`，引用为空；简历及授权范围内没有相关技术证据。
此结论仅依据简历与“没有已授权补充材料”，不否认候选人能力。

**用户交互。** 场景名为 waiting_user，但 `user_reply=null`，不允许代替用户编造回答。
如果实际进入 ASK_USER，应保持等待，而不是假装补证或完成。技能状态与等待状态是两个维度。

**歧义。** 场景意图需要澄清，不等于 cases.json 已提供“唯一正确行动”的正式标签。

**建议人工重点检查。** 是否确认技能 Gold 为 not_found，同时把 waiting_for_user 单独审视？
若未来审查行动质量，是否还需要独立的行动标注，而非从技能状态反推？本次不新增此类标签。

人工结论：**待复核**。

## 案例 08 — unverified_reply

**JD 要求及条件。** [jd.md:2](../examples/evaluation/08/jd.md)：

> Required: SQL.

JD 本身没有要求生产经验。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/08/resume.md)：

> Fictional candidate Hazel. I designed a poster.

**授权补充材料。** 无。

**文件事实/口头声明对照。**

| 资料类型 | 内容 | 可用于什么 |
| --- | --- | --- |
| 简历文件 | 上述海报设计陈述，没有 SQL 信息 | 支持“当前文件缺少 SQL 证据”的观察 |
| 允许的模拟用户回复 | I say I wrote production SQL queries, but cannot provide a file or original excerpt. | 作为待核实线索；不是已验证项目文件证据 |

**当前 Gold 及依据。** SQL `not_found`，引用为空。回复包含正向能力主张，但没有新增可验证文件或原文，
不能把该口头声明提升成 supported/partial 的文件证据。标签以简历的缺证为基础，交互不改变文件事实。

**歧义。** 真实系统也许愿意记录“用户自述能力”，但这是独立的可信度层次；不能和当前文件证据状态混用。
回复提到 production 也不能反过来为 JD 增加未写的生产要求。

**建议人工重点检查。** 是否认可回复前后保持 not_found，同时单独保留未经核实声明？
是否清楚区分“有声明”“声明真假未定”和“已有文件证据”？

人工结论：**待复核**。

## 案例 09 — fabricated_citation

**JD 要求及条件。** [jd.md:2](../examples/evaluation/09/jd.md)：

> Required: Python.

没有另列生产服务或项目年限要求。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/09/resume.md)：

> Fictional candidate Indigo. I designed a poster.

**授权补充材料。** 无。

**当前 Gold 及依据。** Python `not_found`，引用为空；实际输入文件没有 Python 实践。
场景名称中的“虚构引用”是待测试的模型行为，不是可以加入事实证据的新材料。
即使模型没有生成虚构引用，这个基于文件缺证的标签也不改变。

**用户交互。** 没有配置回复。如果系统选择提问，不能自行填入“会 Python”的答案。

**歧义。** Gold 的 not_found 是对完整文件事实的分类；系统若因自己的非法引用而返回 uncertain，
描述的是判断失败，不自动成为 Gold 所需的“文件事实有矛盾”。两者应由人工区分。

**建议人工重点检查。** 能否明确把“无证据”“模型编造”和“文件里出现矛盾”分开？
标注不得取决于某次 Mock 是否编造、怎么编造或最终打了什么分。

人工结论：**待复核**。

## 案例 10 — permission_failure

**JD 要求及条件。** [jd.md:2](../examples/evaluation/10/jd.md)：

> Required: RAG.

没有明示生成环节、检索指标阈值或部署条件。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/10/resume.md)：

> Fictional candidate Juniper. I wrote a newsletter.

**授权补充原文。** [rag.md:1](../examples/evaluation/10/rag.md)：

> I implemented RAG retrieval with citations and evaluated retrieved document IDs.

**当前 Gold 及依据。** RAG `supported`；补充句子标为 `supports`，依据为本人检索实现、引用与检索文档 ID 评估。
简历单独不支持这个结论，标签依赖完整授权补充材料。

**运行条件与歧义。** 该文件在 authorized_sources 中，另配置 `fault=access_denied`。
这不是一个“未经用户授权却被作为 Gold 证据”的案例，而是对已授权文件注入运行期拒绝。
现行标注约定以完整文件事实为参考，即使系统读不到，标签仍为 supported；正常拒绝访问与技能分类错误
是不同评价维度。另有与案例 02 相同的 RAG 覆盖不全歧义：原文没有明确生成/增强环节。

**建议人工重点检查。** 是否接受“事实标签使用完整授权材料，而执行时故意不可读”的评测口径？
是否需要在解释准确率时明确这是信息获取失败，而非能力推断失败？RAG 满足门槛是否与案例 02 一致？

人工结论：**待复核，优先确认权限故障口径与 RAG 门槛**。

## 案例 11 — tool_failure

**JD 要求及条件。** [jd.md:2](../examples/evaluation/11/jd.md)：

> Required: SQL.

没有真实业务或生产部署条件。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/11/resume.md)：

> Fictional candidate Kestrel. I edited an article.

**授权补充原文。** [sql.md:1](../examples/evaluation/11/sql.md)：

> I wrote SQL JOIN queries and verified each aggregate against expected rows.

**当前 Gold 及依据。** SQL `supported`，补充原文关系为 `supports`。
依据是本人 JOIN 查询与聚合结果检查，采用与案例 01 类似的实践门槛；简历单独无 SQL 证据。

**运行条件与歧义。** 配置 `fault=io_error`，人为模拟工具不可读；完整授权文件中的实践陈述仍作为事实参考。
“运行中未读到”和“全量授权材料中没有”不是同一件事。JD 宽泛带来的满足深度问题与案例 01 相同。

**建议人工重点检查。** 是否认可该自述足以满足宽泛 SQL 要求？
I/O 失败是否只影响执行状态，而不改变事实 Gold？需与案例 10 的权限故障口径一致。

人工结论：**待复核**。

## 案例 12 — invalid_action

**JD 要求及条件。** [jd.md:2](../examples/evaluation/12/jd.md)：

> Required: SQL.

没有部署环境或真实业务条件。

**Resume 相关原文。** [resume.md:1](../examples/evaluation/12/resume.md)：

> Fictional candidate Linden. I wrote a newsletter.

**授权补充原文。** [sql.md:1](../examples/evaluation/12/sql.md)：

> I wrote SQL JOIN queries and verified their output with fixture-based tests.

**当前 Gold 及依据。** SQL `supported`；补充句子标为 `supports`，依据为本人查询及基于测试数据的结果校验。
标签依赖补充材料，原简历独立不足以支持。

**歧义。** fixture-based tests 不证明生产经验，但该 JD 没有要求生产经验；不能把案例 05 的条件移植过来。
invalid_action 是行为测试场景，不是候选人技能属性；一次参数错误不应改变事实 Gold。
当前 Gold 不包含“必须纠正几轮”“必须选择何行动”等行为答案。

**建议人工重点检查。** 是否同意测试数据下的查询实践已满足这个 JD？
是否与案例 05 的 partial 差异完全来自 JD 的额外条件，而不是对测试数据或合成数据的任意偏好？
标注是否独立于模型有无犯参数错误？

人工结论：**待复核**。

## 待人工复核的问题清单

以下优先级只表示对标注一致性的影响，不表示建议替换任何具体标签。

- [ ] **高：宽泛 JD 的满足门槛。** 案例 01、02、04、06、10、11、12 只写技能名；
  是否统一接受“有具体、本人执行的文档自述”作为充分实践？不得把推断的门槛说成 JD 明示条件。
- [ ] **高：完整 RAG 的边界。** 案例 02/10 的检索、引用和评估是否足够？
  是否必须补充 generation/augmentation 才能 supported？应先确定标准，再审查这两个标签。
- [ ] **高：否定与不确定的边界。** 案例 04 的教程与未写查询是否真的矛盾？
  与案例 06 的本人职责排除相比，为什么一个 uncertain、一个 not_found？请按一致原则裁定。
- [ ] **高：限制句的关系含义。** 案例 05 的生产限制被标为 partial，究竟表示限制完整满足，
  还是也允许它单独作为 partial 能力的正向引用？请同时检查状态标签与证据关系，避免混为一谈。
- [ ] **高：故障时 Gold 的事实范围。** 案例 10/11 是否认可使用完整授权但运行期不可读的文件？
  解释结果时应区分技能判断质量与环境故障，不能通过改标签掩盖故障。
- [ ] **中：团队参与与本人实践。** 案例 06 写文档是否可能算基础 Docker 知识？
  irrelevant 是否意指“不支持个人实践”而非“语义完全无关”？
- [ ] **中：用户陈述的可信度层次。** 案例 03/04/05/08 的回复只提供未核实信息。
  是否一致地不把口头声明或“没有文件”转换成能力有无的事实？
- [ ] **中：缺证、矛盾与系统自身错误。** 案例 03/07/08/09 的 not_found 与案例 04 的 uncertain
  是否按同一标准区分？模型编造引用不能变成输入材料里的矛盾。
- [ ] **中：技能粒度与分母。** 是否认可案例 05 仍只算一个复合 SQL 标签、案例 01 算两个？
  当前全为 required、无 preferred；13 项的技能微平均不等于 12 个案例的宏平均。
- [ ] **中：交互与行动 Gold 的缺口。** waiting_user 等场景名不是正式行动标签；
  `user_reply=null` 也不表示允许系统代答。技能准确率不能单独证明 ASK_USER/FINISH 选择正确。
- [ ] **通用：来源归属与验证强度。** 各补充文件的 “I” 被约定为同一案例候选人，未独立核实身份、
  代码或测试结果。授权可读、引用可定位、语义相关、实际能力真实是四个不同层次。

建议人工在独立复核记录中分别填写“接受/存疑/建议修订、理由、所引原文”，先确定上述标准，
再裁定单项标签；不得以提高任何一种方法的得分为理由。若未来决定修改标签，按 GOLD_NOTES 的约定
另行记录数据集版本与复核依据。本稿不执行改标、重跑评测或结果更新。
