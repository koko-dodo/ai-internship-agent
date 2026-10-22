# Development notes and engineering trade-offs

This document distills the earlier README's implementation history. It is not
a release chronology or a claim that the system is ready for hiring decisions.
The project scope is one Resume/JD pair, explicit supporting files, and a small
reproducible comparison of policies. See [Architecture](ARCHITECTURE.md) for
current contracts and [Evaluation](../evaluation/README.md) for measurements.

## Why a custom Agent Loop?

The engineering question was how a model-driven action policy could gather
missing evidence while Python retained execution authority. A fixed workflow
alone would not expose model-selected actions, Tool Call/result correlation,
recoverable argument failures or interactive continuation. Writing the small
loop directly made those responsibilities inspectable and testable without
LangGraph, LangChain or an orchestration dependency.

This does not make an Agent preferable for every task. The fixed workflow is
an implemented baseline with the same authorized data and evidence machinery.
Predictable work can be handled more cheaply by its deterministic policy;
autonomous selection needs to earn its additional model requests. The purpose
of the comparison is to test that trade-off, not justify autonomy by definition.

## Tools and typed execution first

The first layer implemented constrained TXT/Markdown reading, basic rule-based
JD parsing and literal evidence lookup. These are deliberately modest tools:
`parse_job` is not semantic understanding, and a keyword hit is not proof.

Tool registration is explicit. Parameter JSON Schemas come from the Pydantic
models that also validate execution. This avoids drifting definitions between
the prompt and Python. Unknown tools and malformed arguments become structured
errors; the model never chooses an arbitrary callable. Path failures stop
rather than prompting the model to search elsewhere.

The provider-neutral LLM interface came next. Mock responses and exceptions
made call ordering, multiple calls, IDs, skipped batch items, loops and failures
testable offline. The DeepSeek adapter implements the same interface through
the OpenAI-compatible SDK. Provider JSON decoding and transport errors stay
outside the loop; secrets and raw SDK exceptions stay outside diagnostic logs.

## From text generation to auditable matching

Matching separates three responsibilities:

1. The LLM extracts requirements and proposes skill states with verbatim quotes.
2. Python checks source text, line locations and snapshot integrity, then applies
   conservative guards for unsupported positive claims.
3. A deterministic weighted function calculates the score from validated states.

The `match_resume_to_job` tool binds the resume, JD and allowed directory in
application code, exposing no replacement text/path/score parameters. This
integrates semantic matching with Tool Calling without allowing the model to
rewrite task inputs. It also means a tool can make nested LLM calls; those
must be included in the shared budget rather than hidden behind one Agent step.

## Failure cases that changed the design

| Observation | Fix and remaining boundary |
| --- | --- |
| SQL查询 and SQL used different retrieval names | Match recognized skill tokens with boundaries inside descriptive search phrases; do not treat this as universal skill equivalence. MySQL/NoSQL remain distinct |
| SQL practice and synthetic/no-production limitations were mixed | Separate skill denial from missing job subconditions. Preserve positive practice plus limits; real contradictory evidence may still reduce the score |
| Models repeated the same search after success | Send search history, failed-pair reasons and remaining legal choices; Python independently blocks repeat reads and stops persistent no-progress retries |
| ASK_USER on the last initial round could not resume | Add a one-time, finite recovery window within the same remaining request budget; no unlimited reset |
| ASK_USER reused overly narrow target validation | Define action-specific parameters; unresolved partial/not_found/uncertain skills are askable, FINISH needs no target, and non-skill targets remain unsupported |
| Malformed actions terminated too early | Give structured feedback and at most two correction opportunities, still charging requests and rounds |
| SQL querying was marked unexpected by evaluation | Add opt-in skill-alignment-v2 with complete aliases and explicit JD-bound conditions; retain raw outputs and historical metrics |

These cases are covered by offline tests. Rule guards remain imperfect for
scope, temporal changes, ownership and nuanced contradictions. None verifies
whether fictional or real source documents are truthful.

## Evaluation before performance claims

The fixture draft preceded the evaluator. User-supplied independent semantic
review decisions then produced frozen gold-v1: 12 fictional cases and 13 skill
labels, supported by exact evidence annotations. This was one review, not a
multi-annotator study. The [change record](../evaluation/GOLD_CHANGELOG.md) preserves
the SQL denial correction and full RAG material revision, with an archived draft.
No labels were changed to improve Mock accuracy.

Single sees only Resume/JD. Fixed and Agent share semantic assessment, authorized
data, verification, deterministic scoring and reply fixtures. Fixed chooses
actions by rules; Agent uses LLM decisions. Evaluation initializes both directly
with the Matcher so tool-routing overhead does not bias the policy comparison.
Independently sampled model judgments still confound causal interpretation.

Two saved live DeepSeek cases illustrated the trade-off:

- Case 02: Fixed used 2,125 tokens; Agent used 4,488. Agent avoided one empty
  file search, but both matched the complete RAG requirement correctly.
- Case 05: Fixed used 2,083 tokens; Agent used 7,266. Both recognized partial
  SQL practice, but different skill decompositions and naming affected the
  original accuracy metric. Agent also performed a second, empty search.

Under the explicitly post-hoc skill-alignment-v2 protocol, Fixed and Agent are
correct on both cases. The recorded responses did not improve: re-scoring
changed representation alignment, not the models. Original reports remain
available. The [live analysis](../evaluation/reports/LIVE_ANALYSIS.md) explains
the raw 1/2 versus 0/3 result and evidence-annotation coverage limits.

## One conservative context optimization

Action decisions dominated case 05's tokens, but the decision payload already
excluded full resume/project documents. Rather than alter action policy or
remove safety context, the implementation only removed JSON formatting spaces
outside strings for action requests.

Offline saved-response replay reduced decision-context characters from
6,115 to 5,738 for case 02 and 13,672 to 12,837 for case 05. Calls, retrievals,
states, citations and interactions stayed unchanged. These are reconstructed
offline character counts, not historical HTTP measurements or actual token
savings. Fixed Mock responses cannot establish how a real model reacts to a
new prompt. See the [A/B documentation](../evaluation/TOKEN_COST_OPTIMIZATION.md).

## Current validation and public-release boundary

The offline suite passes 545 pytest cases. It covers ID association, strict
schemas, denied paths, duplicate searches, invented evidence, contradictory
context, scoring, waiting/resume, request budgets, fault scenarios and report
reproducibility. Adapter tests inject Fake SDK behavior; they do not call APIs.

The author confirmed that `examples/resume.txt` is an anonymized, simplified
sample adapted from their real education and project experience and authorized
its publication. Its original content is preserved; it is not a fictional
evaluation fixture. The author also approved publication of the existing Git
author email. Neither Git identity configuration nor commit history was changed
to address those items.

Known trade-offs include synchronous execution, in-memory-only continuation,
literal search, sparse semantic annotations, no hard currency cap and no
operating-system isolation. There is no evidence of overall Agent superiority
over the fixed workflow. Larger controlled experiments would be needed before
making that claim; they are outside this documentation task.
