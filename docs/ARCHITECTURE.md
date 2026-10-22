# Architecture and execution contracts

This project separates model proposals from executable authority. The model can
request registered tools or propose evidence judgments; Python owns validation,
file authorization, scoring, state transitions and budgets. There is no Agent
framework, database, application submission service or background scheduler.

## Modules

| Module | Responsibility |
| --- | --- |
| [schemas.py](../src/schemas.py) | Pydantic tool arguments/results, job requirements, citations, match states, scores and gathering decisions |
| [llm.py](../src/llm.py) | Provider-neutral messages, tool calls, responses, client Protocol and scripted Mock |
| [deepseek.py](../src/deepseek.py) | OpenAI-compatible SDK transport, argument JSON decoding, call IDs, sanitized provider errors and request caps |
| [agent.py](../src/agent.py) | Bounded synchronous Tool Calling loop and metadata-only trace |
| [tool_registry.py](../src/tool_registry.py) | Explicit registration, argument validation, generated Tool Schemas and uniform execution results |
| [tools.py](../src/tools.py) | Authorized text reading, rule-based JD parsing and literal resume evidence lookup |
| [matching.py](../src/matching.py) | Semantic JD extraction, initial assessment, exact quote validation, report building and deterministic scoring |
| [evidence_search.py](../src/evidence_search.py) | Explicit supplemental-file grants, literal candidate search, source snapshots and file/skill deduplication |
| [autonomy.py](../src/autonomy.py) | SEARCH / ASK_USER / FINISH state machine, supplemental assessment and bounded in-memory resume |
| [evaluation/](../evaluation/README.md) | Frozen fixtures, method adapters, observational metrics, versioned re-scoring and reports |

## Provider-neutral interface

`LLMClient.complete(messages, tools) -> LLMResponse` is a synchronous Protocol.
The response contains either a nonempty final answer or one or more Tool Calls,
never both. `ToolCall` carries an ID, tool name and argument object. Message
validation enforces role-specific payloads and matching tool-result IDs.

`ToolRegistry.register(name, arguments_model, handler, description=...)` accepts
only explicitly supplied handlers. `get_tool_schemas()` derives the parameter
JSON Schema from the same Pydantic model used by `execute(name, arguments)`.
There is no second parameter definition and no arbitrary Python evaluation.
Execution returns `tool_name`, `success`, `data` and an optional structured error.
Strict argument validation rejects unknown fields and wrong types.

`DeepSeekLLMClient` maps these types to SDK messages and function definitions,
retains call IDs, and decodes JSON argument objects. Duplicate JSON keys,
non-finite values, invalid responses and truncated output are rejected. Timeout,
connection and provider failures use sanitized diagnostic codes. SDK retries
are disabled for the configured real client. Credentials come from the process
environment; modules do not load `.env`. The adapter supports synchronous,
non-streaming, non-thinking requests. Mock responses/exceptions are preset;
they are not autonomous model reasoning.

## Actual execution paths

### General Tool Calling loop

`Agent(client, registry, max_steps).run(task)` sends a copy of message history
and current Tool Schemas to the client. It validates the complete response,
appends the assistant's Tool Calls, then executes their handlers sequentially
through the registry. Each result is appended with its original call ID.
The model then selects another tool or returns final text.

Call IDs must be unique across the run. A fatal failure skips remaining tools
in that batch while appending ID-correlated `not_executed` results. A final
answer produces `completed`; exhausting steps produces `step_limit`, never a
fabricated successful answer. Tool count is not the same as model-step count.

### Initial evidence matching

`EvidenceBasedMatcher.match()` reads one application-bound resume inside its
allowed directory, extracts the JD with one structured model request, and
assesses its skills with another request. The assessment call is skipped for
an empty extracted skill list. The model proposes exact quotes and states;
Python validates them and builds the evidence report.

`create_matching_registry(matcher)` exposes `match_resume_to_job` with an empty
argument object. The model cannot replace the bound resume/JD, change the
allowed directory or provide a numeric score. The matching demo and
`start_cost_aware_matching()` route this registered tool through `Agent`.
Semantic requests made inside the tool also consume the shared request budget.
Assistant confirmation text is separate from the validated tool report.

### Supplemental evidence gathering

`EvidenceGatheringSession` receives the initial report, its exact resume
snapshot, a `BudgetedLLMClient` and a `ProjectEvidenceSearch`. It verifies the
resume hash and preserves a deep copy of the initial report.

1. Python computes current gaps, legal unsearched file/skill pairs, costs,
   askable skills, remaining budgets and allowed actions.
2. The LLM returns a `GatheringDecision` and short reason. Python validates the
   action-specific shape and target. Only unresolved skills are askable;
   non-skill questions are not implemented.
3. SEARCH passes through the registered search executor. Empty results skip
   supplemental model assessment. Candidates trigger a structured assessment
   using authorized snapshots plus the original resume.
4. Python verifies quotes, applies conservative evidence guards, recalculates
   scores and preserves a change record. The next round receives state and
   tool feedback, not the full evidence documents.
5. ASK_USER returns `waiting_for_user`. FINISH returns `finished` with the
   current report. Other terminal statuses remain distinct.

Action-decision JSON uses compact separators only. Parsed instructions,
Schema/data values and string contents are unchanged; semantic assessment
prompts retain their original format. See the [offline A/B record](../evaluation/TOKEN_COST_OPTIMIZATION.md).

### Evaluation is a controlled variant

The evaluation adapters call `EvidenceBasedMatcher.match()` directly for both
Fixed and Agent initialization, excluding the initial tool-routing conversation
from both methods. They then use the same gathering controller. Fixed replaces
only action selection with Python rules; it still searches authorized files,
assesses retrieved evidence and can ask the user. Single uses one model call
with Resume/JD only and retains its unverified judgments and optional score.

This aligns capabilities, not random outcomes: live semantic calls are sampled
independently. Different initial checkpoints prevent policy-only causal claims.
Evaluation-only skill-alignment-v2 does not alter production skill names,
decisions, evidence, scores or original model responses.

## Evidence, authorization and scoring

`validate_quote()` requires an exact original substring and produces a source,
line span, context and content hash. Invalid positive evidence cannot support
a fully satisfied requirement. Source existence does not establish ownership,
truthfulness or semantic sufficiency; those remain separate concerns.

The original reader resolves paths and symlinks against an application-configured
allowed directory and accepts UTF-8 TXT/Markdown. Supplemental search is stricter:
individual examples-relative grants, no hidden/traversing paths, no symlinks,
TXT/Markdown only, and a 64 KiB per-file cap. It does not crawl directories.
Candidate hits include original text, source, line and snapshot hash. A keyword
hit is not a skill judgment. Retrieval alias matching is distinct from skill
identity in evaluation: SQL can be found in a descriptive query without equating
all SQL-related job conditions with SQL.

Supplemental quotes must belong to allowed, searched snapshots. Clause-level
guards distinguish denial of a skill from limitations such as synthetic data
or no production deployment. Restrictions alone cannot establish positive
practice. Contradictions can lower a score; the system does not force scores
to increase. These guards are limited rules, not a general semantic verifier.

Default weights are 2 per required skill and 1 per preferred skill. Credits:

| Status | Credit | Meaning |
| --- | ---: | --- |
| supported | 1 | Evidence supports the complete requirement |
| partial | 0.5 | Some practice/knowledge or incomplete condition coverage |
| not_found | 0 | Insufficient current evidence; not a claim of inability |
| uncertain | 0 | Unresolved ambiguity or contradictory evidence |

`score = round(100 * sum(weight * credit) / sum(weight), 2)`

`score_matches()` accepts structured states, not model-supplied scores. Duplicate
skills count once; conflicting duplicate states become uncertain, and required
category takes priority. Weight normalization prevents overflow without changing
the ratio. Empty requirements yield `score=0, applicable=false`. The score is
evidence coverage, not hiring probability or measured classification accuracy.

## Human interaction, budgets and errors

Waiting sessions are inert until an explicit nonblank reply. Replies remain
`verified=false`, do not become file evidence and cannot grant paths embedded
in text. Additional grants require the separate application argument
`resume(answer, additional_sources=...)` and the same authorization checks.

Gathering defaults: 5 initial decision rounds, at most 3 searches, and a shared
12-attempt LLM budget. The first reply opens one recovery window of at most
2 new rounds, bounded by remaining requests; it does not refill search/request
quotas or restore unused initial rounds. The window cannot reset repeatedly.
Sessions and snapshots are in memory only. Provider request/output caps are
not a monetary cap; input context can also be billable.

| Failure | Policy |
| --- | --- |
| General-loop unknown tool / invalid arguments / invalid input | Return structured feedback within the original step budget |
| General-loop access denied / missing file | Stop; do not reconstruct paths or scan for replacements |
| Gathering invalid action shape/target | At most two correction opportunities across the whole session |
| Duplicate search / exhausted search quota | Feedback with history; two consecutive unavailable searches stop with no-progress error |
| Gathering permission denial | Stop immediately without a fallback path |
| Other tool failure / invalid supplemental response / model exception | Explicit tool/model error; preserve progress |
| Exhausted requests or rounds | `budget_exhausted` / `step_limit`; not successful completion |

Sanitized traces omit raw parameters, evidence, user answers and SDK exception
text. Full messages, Mock request snapshots and report artifacts can contain
input material and must not be treated as safe diagnostic logs. File guards
are not an operating-system sandbox against concurrent malicious replacement.
Public examples need explicit publication review: evaluation fixtures are
synthetic; the legacy example resume is an author-approved anonymized sample.
