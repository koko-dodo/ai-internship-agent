# Gold 数据版本记录

## day6-v1（历史草稿）→ gold-v1（独立复核后冻结）

独立语义复核决定由用户提供，编码助手落实。不是多人标注或专家委员会，未计算标注者一致性。
新目标为“完整授权文件是否足以支持满足 JD 明示技能条件”，不是现实能力核验。
本次决定先确定数据与标签，再运行评测；不得根据新 Mock 结果再次调标。

| 项目 | 草稿 | 冻结 Gold v1 |
| --- | --- | --- |
| 版本 | day6-v1 | gold-v1 |
| 标签状态分布 | supported 6 / partial 1 / not_found 5 / uncertain 1 | supported 6 / partial 1 / not_found 6 / uncertain 0 |
| 案例 04 SQL | uncertain；否定关系 contradicts | not_found；否定关系 negates |
| 案例 05 SQL | partial；生产限制关系 partial | partial；生产限制关系 limits |
| 案例 02/10 | supported；证据只明确检索和引用 | supported；材料补足 R/A/G 三环节，JD 不变 |
| 其余案例 | 01、03、06、07、08、09、11、12 | 标签、理由、原文均保留 |

## 案例 04：理由变更，原文保留

原状态：`uncertain`；原否定关系：`contradicts`。原理由：

> Introductory study exists, but the project explicitly denies candidate-owned querying; verify ownership rather than infer competence.

新状态：`not_found`；新否定关系：`negates`。新理由：

> Completing a basic tutorial does not necessarily imply writing SQL queries. The authorized project explicitly denies candidate-owned query practice; there is no necessary contradiction. Under the independently reviewed standard, the required practice is not substantiated.

教程与否定句未修改；不将没有查询实践误说成与基础学习必然冲突。

## 案例 05：实践与限制分开

状态仍为 `partial`；教程和查询实践的 `partial` 保留。只有下句的关系从 `partial` 改为 `limits`：

> The project used synthetic data and was not deployed to production.

该句可限制生产子条件、帮助解释 partial，但单独不能证明本人查询实践。

## 案例 02：冻结前修订完整 RAG 材料

来源：`evaluation/02/b_rag.md`。JD 仍为 `Required: RAG.`；Gold 仍为 `supported`。

旧证据：行 1–1，关系 supports：

```text
I implemented RAG retrieval with document citations and tested retrieval against a fixed set of questions.
```

新证据：行 1–3，关系 supports：

```text
Retrieval: I implemented RAG retrieval with document citations and tested retrieval against a fixed set of questions.
Augmentation: I inserted the retrieved passages into the LLM prompt as context.
Generation: I called the LLM with that context to produce answers with citations to the retrieved documents.
```

这是对虚构输入材料的明确补全，不是把旧的检索/引用描述追认成已包含完整 RAG。

## 案例 10：冻结前修订完整 RAG 材料

来源：`evaluation/10/rag.md`。JD 仍为 `Required: RAG.`；Gold 仍为 `supported`。

旧证据：行 1–1，关系 supports：

```text
I implemented RAG retrieval with citations and evaluated retrieved document IDs.
```

新证据：行 1–3，关系 supports：

```text
Retrieval: I implemented RAG retrieval with citations and evaluated retrieved document IDs.
Augmentation: I inserted the retrieved passages into the LLM prompt as context.
Generation: I called the LLM with that context to produce answers with citations to the retrieved documents.
```

这是对虚构输入材料的明确补全，不是把旧的检索/引用描述追认成已包含完整 RAG。

## 故障、兼容与脚本记录

案例 10/11 保留事实 Gold 与 `access_denied`/`io_error` 配置；报告另列非故障子集及实际故障关闭配对运行。
不更改 Agent、Workflow 的行动策略、证据验证或确定性评分，也不为任何方法覆写预测状态。
证据枚举新增 `limits`、`negates`，旧的 supports/partial/contradicts/irrelevant 仍可加载。
Mock 只同步案例 02/10 的 supplemental 引文为新原文；所有预设状态、行动、理由、分数保持原样，
包括案例 04 仍返回 uncertain。脚本不作为 Gold 决策来源。

## 冻结及结果归档

旧的 39 个数据/文档/脚本/结果文件已原样归档于 `versions/day6-v1-draft/`，
对应 ARCHIVE.json 保存原文件 SHA-256。旧报告保留原口径，不用新指标重写历史结果。
新标签与材料确定后，由 GOLD_V1_FREEZE.json 记录 37 个 Gold 文件的哈希及数据集指纹。
清单本身、Mock 脚本、代码和评测报告不纳入 Gold 文件哈希；默认加载校验，不自动刷新哈希。
离线重跑输出写入 `reports/mock.json`/`mock.md`；新旧结果及差异归因另见
[reports/gold-v1-comparison.md](reports/gold-v1-comparison.md)，该结果文件不改变已冻结标注。
