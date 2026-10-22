# Gold Label Audit — 独立复核后的 Gold v1

## 独立复核状态与范围

本稿已从初始审计准备稿更新为 **gold-v1 独立语义复核记录**。复核决定由用户提供，
编码助手据此落实；不声称多人标注、多个专家共识或标注者一致性统计。
目标是“当前完整授权材料是否足以支持候选人满足 JD 明示技能条件”，不是验证候选人真实能力。

初始 `day6-v1` 的审计准备稿、原始标签、全部 33 份原文、Mock 脚本与报告已原样归档于
[versions/day6-v1-draft/](versions/day6-v1-draft/)。详细前后变化见 [GOLD_CHANGELOG.md](GOLD_CHANGELOG.md)。
下文保留的歧义/检查问题用于记录复核背景与适用边界；最终标签以用户给出的复核决定为准。
不因评测方法或 Mock 输出重新解释标签。

来源定位仍采用“文件名:行号”。冻结范围为 cases.json、全部 33 个输入文件及三份 Gold 说明文件；
最终 SHA-256 与数据集指纹见 [GOLD_V1_FREEZE.json](GOLD_V1_FREEZE.json)。该清单在材料、标签和本文
最终确定后生成，不将自身纳入哈希，避免自引用。引用定位只验证文字存在，不证明现实能力。

## 为什么是 12 个案例、13 个技能标签

计数单位是 **案例 × Gold 技能**，而不是案例、关键词、引用或具体子条件。
案例 01 有 Python、SQL 两项，其余 11 个案例各一项：`2 + 11 × 1 = 13`。

| 统计维度 | 当前数量 |
| --- | --- |
| 技能类别 | Python 2；SQL 7；RAG 3；Docker 1 |
| 状态 | supported 6；partial 1；not_found 6；uncertain 0 |
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

复核后的适用边界：当前使用复合技能粒度与微平均；没有任何 preferred 标签，
不能据此评价“仅缺低优先级加分项时是否值得检索”。本次不扩展标签数量或更改准确率分母公式。

## 标签依赖与交互一览

“依赖补充材料”包括必须检查材料才能确认缺证或限制，不能只理解为正向证据。
用户回复仅是允许使用的模拟陈述，只有系统实际提问后才交付；不是已验证文件证据。

| 案例 | 当前 Gold | 标签依赖 | 用户交互/运行条件 |
| --- | --- | --- | --- |
| 01 | Python supported；SQL supported | 简历足以支持；补充 notes 无关 | 未配置回复 |
| 02 | RAG supported | 依赖 b_rag.md；a_notes.md 为无关材料 | 未配置回复 |
| 03 | SQL not_found | 简历与授权 notes 均无相关证据 | 配置“没有更多可授权文件”的回复 |
| 04 | SQL not_found | 简历学习线索 + 补充材料的实践否定 | 配置“无法提供查询归属证据”的回复 |
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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

## 案例 02 — supplement_available

**JD 条件。** [jd.md:2](../examples/evaluation/02/jd.md) 保持原文：

> Required: RAG.

**Resume 原文。** [resume.md:1](../examples/evaluation/02/resume.md)：

> Fictional candidate Birch. I built a text formatting utility.

**授权材料。** [a_notes.md:1](../examples/evaluation/02/a_notes.md) 仍为无关材料：

> Fictional team schedule and meeting agenda.

[b_rag.md:1–3](../examples/evaluation/02/b_rag.md) 已在正式冻结前补全为：

> Retrieval: I implemented RAG retrieval with document citations and tested retrieval against a fixed set of questions.
> Augmentation: I inserted the retrieved passages into the LLM prompt as context.
> Generation: I called the LLM with that context to produce answers with citations to the retrieved documents.

**当前 Gold 与依据。** RAG `supported`。引用是完整三行，关系为 `supports`；本人完成检索、
把检索片段加入 LLM 上下文，再生成带文档引用的回答。该结论依赖补充材料，不能从原简历推出。

**独立复核决定。** 原稿只写检索与引用，不足以清晰表达完整 RAG。按用户决定修订虚构材料，
而不是放宽 JD 或追认旧引文足够；旧句及旧证据行号保存在版本归档与 CHANGELOG。

**适用边界。** 不新增实际效果阈值、生产部署要求或真实能力验证。这里接受具体本人实践的案例内文件自述；
三环节是否被逐字引用与三环节技术描述是否相关仍是两个不同检查。

结论：**按独立复核决定补全材料，保留 supported；非待定标签**。

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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

## 案例 04 — negation

**JD 条件。** [jd.md:2](../examples/evaluation/04/jd.md)：

> Required: SQL.

**学习线索与实践否定对照（原文未改）。**

| 来源 | 原文 | Gold v1 关系 | 解释 |
| --- | --- | --- | --- |
| [resume.md:3](../examples/evaluation/04/resume.md) | I completed a basic SQL tutorial. | partial | 有基础知识线索，不必然意味着本人编写过查询 |
| [sql.md:1](../examples/evaluation/04/sql.md) | I have never written SQL queries; the teammate authored all queries in the project. | negates | 明确否定本人查询实践；并非与教程记录必然冲突 |

**Gold 变化。** SQL 从 `uncertain` 修订为 **not_found**。理由为：完成教程与未编写查询可以同时为真，
不能仅因出现否定就推断实质矛盾；在当前标准下，所需本人查询实践没有足够文件支持，且被明确否定。
此结论仍结合简历与授权项目材料，不是断言候选人在现实中没有 SQL 能力。

**用户回复（未经核实，原文未改）。**

> I cannot provide evidence of query ownership.

不能提供归属证据不会补足正向实践，也不额外证明候选人能力有无。

**关系变化。** 否定句从 `contradicts` 改为 `negates`，为真正的实质矛盾/归属冲突保留 `contradicts`。
旧理由、旧关系、旧状态与全文均已归档。Mock 的 uncertain 判断未为提高得分而改为 not_found。

**适用边界。** 若未来文件明确一处声称本人写过同一查询、另一处否定同一归属，才需按新标准审视 uncertain；
本例没有这样的明确冲突。与案例 06 一样，不把团队实践自动转给候选人。

结论：**按独立复核决定修订为 not_found；非待定标签**。

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
| [sql.md:3](../examples/evaluation/05/sql.md) | The project used synthetic data and was not deployed to production. | limits | 对这个项目的数据及部署环境作限制，不否定 SQL 查询实践 |

**当前 Gold 及依据。** SQL `partial`：具体查询实践有支持，而真实业务/生产环境子要求没有被满足或证明。
不能因未上线就把查询实践本身当成虚构，也不能因做过查询就把环境条件当成满足。
补充材料对该解释是关键。

**用户回复。** 未经核实陈述：

> I have no real business project document to authorize.

这表示没有可授权文件，并不证明候选人在所有经历中都没有真实业务经验。

**独立复核决定。** 保留 SQL `partial`。查询句及教程是正向实践/知识线索，仍用 `partial`；
生产限制句改为 `limits`。限制句只说明当前项目不满足生产子条件，不能单独支持具有部分查询实践，
也不能否定已经存在的查询实践。包含实践与限制的联合引用可以支持整体 partial；只有 limits 的引用不计正向支持。

**适用边界。** 限制只作用于这个项目，不能外推候选人所有经历。一个 SQL 标签仍覆盖 JD 的全部子条件，
不把子条件再算作独立技能或调整准确率分母。

结论：**按独立复核决定保留 partial，限制关系已明确；非待定标签**。

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

独立复核决定：**保留 Docker not_found 与 irrelevant**。不能从团队使用和仅写文档推断本人实践。

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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

## 案例 10 — permission_failure

**JD 条件。** [jd.md:2](../examples/evaluation/10/jd.md) 未改：

> Required: RAG.

**Resume 原文。** [resume.md:1](../examples/evaluation/10/resume.md)：

> Fictional candidate Juniper. I wrote a newsletter.

**授权项目修订后原文。** [rag.md:1–3](../examples/evaluation/10/rag.md)：

> Retrieval: I implemented RAG retrieval with citations and evaluated retrieved document IDs.
> Augmentation: I inserted the retrieved passages into the LLM prompt as context.
> Generation: I called the LLM with that context to produce answers with citations to the retrieved documents.

**当前 Gold 与依据。** 保留 RAG `supported`；证据覆盖全部三行、关系为 `supports`。
原文在冻结前从检索/引用描述补足为本人 Retrieval、Augmentation、Generation 的完整实践链路，
适用门槛与案例 02 相同。原始证据逐字保留在归档与 CHANGELOG 中。

**运行故障与事实标签分开。** 文件仍被明确授权；`fault=access_denied` 是独立注入的运行条件，
不撤销 Gold 对完整授权材料的参考范围，不把读取失败改写成候选人缺技能。
报告保留含故障的整体结果，并区分非故障案例子集及关闭故障后的配对对照；不能把删掉故障案例冒称为重跑结果。

**适用边界。** 单份完整项目自述不是现实能力核验。未来真实模型的故障关闭对照也可能有采样差异，
不保证除权限外所有模型输出都完全相同。

结论：**按独立复核决定补全材料并保留 supported，故障独立记录**。

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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

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

独立复核决定：**保留现有 Gold**。上述问题作为已审阅的适用边界记录，不自动触发改标。

## 独立复核决定与冻结后的适用边界

- 案例 01、03、06、07、08、09、11、12 按用户决定原样保留标签及材料。
- 案例 04 的 not_found/negates 取代 uncertain/contradicts，因教程与未写查询不必然矛盾。
- 案例 05 保留 partial，限制句使用 limits，不得独立充当正向技能证据。
- 案例 02/10 在正式评测前补足完整三环节 RAG，保留 supported；JD 不变。
- 案例 10/11 的事实 Gold 与故障状态分开；报告对正常访问条件作明确分层。
- 引用可定位、语义支持 JD、文档自述可信度、真实能力验证是不同层次；本次只评文件支持程度。
- 13 个标签均为 required，当前没有 uncertain 样本。状态仍保留四类定义，但不能声称覆盖均衡或验证了所有冲突类型。
- 只有一次用户提供的独立语义复核；未声称多人共识或计算标注者一致性。

以上是用户本次明确决定，不再作为悬而未决的标签调整建议。若未来发现新问题，必须另立复核记录与版本；
不得依据某一种方法的 Mock/真实模型得分反复改写本版 Gold。冻结清单不覆盖 Mock 脚本、运行代码或报告，
因此可以修复评测实现并重跑，但必须另外记录代码/脚本差异，不能静默变更 Gold。
