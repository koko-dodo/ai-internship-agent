# Evaluation: protocols, artifacts and limitations

This is a small, author-annotated evaluation harness, not a production platform.
It adds no Agent capabilities and changes no Day 1–5 interfaces or decisions.
All fixture people, employers and projects are fictional and publishable.

The frozen dataset contains **12 cases and 13 skill labels**: case 01 has two
labels and the other cases have one each. Accuracy counts skill labels, not
cases or evidence quotes; unexpected prediction names can increase the legacy
denominator. Labels target the sufficiency of complete authorized documents.

## Dataset and result index

| Artifact | Purpose |
| --- | --- |
| [cases.json](cases.json) | Frozen cases, labels, grants and simulated replies |
| [Gold notes](GOLD_NOTES.md), [audit](GOLD_AUDIT.md), [change record](GOLD_CHANGELOG.md) | Label rationale, independent review decisions and material revisions |
| [gold-v1 seal](GOLD_V1_FREEZE.json) | File hashes and dataset fingerprint; do not edit or automatically reseal |
| [Archived draft](versions/day6-v1-draft/ARCHIVE.json) | Earlier material and results, retained for provenance |
| [Mock report](reports/mock.md), [JSON](reports/mock.json) | Scripted framework checks, not real model accuracy |
| [Live analysis](reports/LIVE_ANALYSIS.md) | Detailed audit of two saved DeepSeek cases |
| [Format optimization](TOKEN_COST_OPTIMIZATION.md), [A/B report](reports/token-cost-format-ab/offline-ab.md), [JSON](reports/token-cost-format-ab/offline-ab.json) | Offline decision-context lengths; no measured token saving |

## Saved live results and post-hoc re-scoring

| Case | Original report | skill-alignment-v2 report |
| --- | --- | --- |
| 02 | [Markdown](reports/deepseek-case02-run01/real.md), [JSON](reports/deepseek-case02-run01/real.json) | [Markdown](reports/deepseek-case02-run01/re-scored-skill-v2/re-scored.md), [JSON](reports/deepseek-case02-run01/re-scored-skill-v2/re-scored.json) |
| 05 | [Markdown](reports/deepseek-case05-run01/real.md), [JSON](reports/deepseek-case05-run01/real.json) | [Markdown](reports/deepseek-case05-run01/re-scored-skill-v2/re-scored.md), [JSON](reports/deepseek-case05-run01/re-scored-skill-v2/re-scored.json) |

| Case | Fixed / Agent original correct/total | Fixed / Agent v2 correct/total | Fixed / Agent requests | Fixed / Agent actual tokens |
| --- | --- | --- | --- | --- |
| 02 | 1/1 / 1/1 | 1/1 / 1/1 | 3 / 5 | 2,125 / 4,488 |
| 05 | 1/2 / 0/3 | 1/1 / 1/1 | 3 / 7 | 2,083 / 7,266 |

Both saved runs used DeepSeek `deepseek-flash`. Actual token usage belongs to
the historical calls. **v2 is a post-hoc evaluation protocol revision, not an
improvement in model responses or model accuracy.** It retains raw predictions,
aligns explicit whole-name aliases, and attaches recognized job conditions only
through explicit JD bindings. See the versioned rules below. Original reports
and source hashes remain available, and model scores are not rewritten.

Only two live cases were run, once per method. Agent avoided one irrelevant
file in case 02, but used more requests/tokens in both. Case 05 initial semantic
checkpoints differ, confounding attribution to action policy. No overall
Agent advantage over Fixed is established. Single has a weaker information set
and must not be interpreted as an equal-information autonomy ablation.

The separate format A/B removes only action-JSON formatting spaces. With fixed
saved responses, reconstructed decision-context lengths are 6,115 → 5,738
characters (02) and 13,672 → 12,837 (05), with identical calls, retrievals and
behavior. These are offline character counts, not historical HTTP prompt
measurements or a real Token-saving rate. Usage for replay is unavailable.

## Dataset first

The initial `day6-v1` fixtures were created before the adapters. The user then
supplied independent semantic review decisions, implemented as frozen `gold-v1`
before rerunning evaluation. This is one independent review, not multiple
annotators or measured agreement. The target is whether complete authorized
files support the explicit JD conditions, not verification of real ability.
See [GOLD_NOTES.md](GOLD_NOTES.md), [GOLD_AUDIT.md](GOLD_AUDIT.md) and
[GOLD_CHANGELOG.md](GOLD_CHANGELOG.md) for decisions and
before/after excerpts. The original draft's 39 input/document/script/result
files remain byte-preserved under `versions/day6-v1-draft/`.

`GOLD_V1_FREEZE.json` seals the final manifest, 33 input files and three Gold
documents (37 files) plus the dataset fingerprint. Default loading and running
reject file or in-memory Gold drift, without automatic resealing. Scripts,
runtime code and reports are excluded from this Gold integrity seal. The
loader additionally validates labels, duplicates, grants, exact quotes and
line spans. Hashes certify content integrity, not semantic truth.

`mock_scripts.json` is separate from gold. It contains deliberately wrong
Docker ownership and invented Python evidence, as well as scripted recovery.
The Fake LLM reads those scripts, never the gold. This is **framework validation,
not measured real-model accuracy**. Do not revise gold when a model disagrees.

Cases 10/11 inject identical access-denied/I/O failures for both multi-step
methods at the tool boundary, without reading the denied file or modifying OS
permissions. These synthetic faults are flagged in every run. They apply in
live mode too. Factual labels use full fixtures, while error status is measured
separately. Single has no retrieval and thus cannot encounter those faults.

Reports separate configured overall runs, the 10-case non-fault subset, and
actual paired fault-disabled controls for 10/11. If every pair is present,
`all_cases_with_controls` replaces the two fault cases with those observed
controls to describe normal access across all 12 cases. A subset alone is
never labeled a fault-disabled rerun. Missing controls are explicit.
Offline controls run automatically for every method. Their Fake scripts add
an explicit control-only FINISH after the original fault-terminated sequence;
they do not silently repair exhaustion in the configured runs. Original
scripted states/actions/scores remain unchanged; only RAG quote text is synced
with the revised materials. Extra control calls appear in `execution_cost`,
separately from the original overall cohort, so cost is not underreported.

## Three methods and the policy ablation

| Method | Inputs | Implementation |
| --- | --- | --- |
| Single LLM | Same resume/JD, no supplements or replies | Exactly one model call, raw JSON text kept; predicted statuses and optional model score are never repaired/rescored. Citations explicitly unverified by the method. |
| Fixed Workflow | Same inputs, explicit grants and simulated reply as Agent | Same Day 4 extraction/evaluation followed by a deterministic rule policy: required gaps before preferred, skill-name/source-name tie breaks; inspect available files until satisfied or capped; ask once for an unresolved required gap, then finish. |
| Autonomous Agent | Same inputs/grants/reply | Same Day 4 initialization, then the unchanged Day 5 `EvidenceGatheringSession`; the LLM chooses SEARCH/ASK_USER/FINISH. Real production traces are preserved. |

Both multi-step methods directly call `EvidenceBasedMatcher.match()` for the
same two-call initialization. The extra Day 4 tool-routing conversation is
excluded from **both**, preventing unrelated routing overhead from confounding
the policy comparison. The deterministic policy supplies action JSON to the
same Day 5 controller instead of asking an LLM. This shared controller executes
and validates fixed actions; it does not make them autonomous. Semantic calls,
quote guards, negation handling, scorer, grants, simulated user reply, search
deduplication and recovery are identical. There is no disabled-SEARCH baseline.

Thus Fixed versus Agent is the **action-policy ablation**, rather than a fourth
method with different tools. No production decision code is changed. JSON
records per-case input/grant/budget equality and initial-state equality. Real
model initialization and subsequent judgments are independently sampled, so
this is a capability-controlled comparison, **not a fully fixed-randomness
causal experiment**. Different initial judgments invalidate a policy-only
attribution; even equal initial states do not guarantee equal later reviews.
Do not attribute access to more files or sampling differences to autonomy.

Multi-step defaults: 12 total LLM attempts per method (initialization included),
3 searches, 5 initial decision rounds, one recovery window of 2 rounds. Fixed
policy decisions cost zero LLM requests; the common round limit still applies.
The existing controller's conservative budget gates are kept for both methods.
Single gets just one call and has a weaker information set; report separately.
Replies are drawn verbatim from the same fixture, cannot authorize new files,
and never become verified file evidence. Missing reply preserves waiting.

## Metrics (no weighted composite)

- **Skill Status Accuracy:** micro correct classifications divided by gold
  skills plus unexpected predicted skill names. Missing and duplicate judgments
  for a gold skill are incorrect; extras and duplicates are also reported.
  Gold uses the complete authorized evidence, so Single's information limit
  matters. Scores and score changes are never used as accuracy.
- **Evidence Validity:** fraction of citations that exist verbatim in an
  authorized source and have correct line/hash fields when supplied. Single's
  scope is resume only; the evaluator's post-hoc audit does not mark its method
  output verified or repair its judgment. No citations => unavailable.
- **Semantic Positive Support:** among reviewed citations used for positive
  judgments, fraction whose manual relation supports that judgment. A partial
  excerpt cannot support `supported`; contradictory excerpts cannot support
  positive claims. `limits` and `negates` are explicitly nonpositive;
  a limit alone cannot support partial practice. A quote combining positive
  practice and its limits can support partial. Full reviewed excerpts must be present in the quote; an
  arbitrary matching keyword is unreviewed. Other wording remains unreviewed,
  with annotation coverage reported rather than assumed correct/incorrect.
- **Task Completion Rate:** `finished / runs`, with `waiting_for_user` and each
  error/limit status counted separately. Finished does not imply correct.
- **Useful Retrieval Rate:** useful attempts / all attempts, including failed
  and duplicate ones. Useful means new, authorized, manually reviewed relevant
  evidence in actual retrieved context (including contradictions), or a correct
  gold-aligned status change with such evidence. Repeated existing evidence and
  irrelevant keywords are not useful. Zero attempts => unavailable.
- **LLM Requests:** actual calls to the model interface including failures,
  excluding deterministic policy outputs. Live API attempts are separately
  provider-adapter counted. API usage is captured at the injected SDK boundary
  without changing DeepSeek Adapter. Missing usage on any attempt => total
  tokens unavailable; usage coverage is retained. No estimation.
- **Latency:** measured end-to-end local execution for each method, excluding
  shared dataset loading/metric auditing. Mock timings have no API meaning.
- **Invalid / Duplicate Actions:** count failed decision/search trace events
  with validation/duplicate/limit codes, without double-counting termination.

Overall metrics pool numerator/denominator counts; scenario groups are reported
separately. JSON includes all predictions, original Single text/score,
interactions, budgets, traces, retrieval audit and evidence audit. No live key
or raw SDK exception is recorded.

## Opt-in skill alignment v2 (saved runs only)

The live case 05 audit exposed two separate issues: full-name synonyms such as
`SQL querying` were not aligned with `SQL`, and a JD condition was emitted as
another skill. The historical evaluator and `evaluation.run` keep their original
rules for reproducibility. `evaluation.alignment` adds **skill-alignment-v2** as
an explicit, offline re-score; it changes no Day 3–5 decisions, prompts, scoring,
raw predictions, citations or model outputs. This is a **post-hoc protocol
revision**, not another model experiment or a performance improvement.

Identity matching uses case/whitespace normalization, the existing whole-name
aliases, and a small versioned complete-alias table (`SQL querying`, `SQL queries`,
`SQL查询`, `SQL 查询`, `SQL query writing`; full Retrieval Augmented Generation
names map to RAG). There is no fuzzy/substring similarity or LLM judge.
NoSQL, MySQL, SQL production experience, retrieval-only, and Docker documentation
are not aliases of SQL/RAG/Docker. Adding vocabulary requires tests and a new
rule version when results change; unsupported expressions remain unexpected.

Conditions are not skill identities. The finite condition ontology currently
recognizes production experience, real-business-data experience, and their
combined phrase. Attachment requires an explicit JD sentence of the form
`<skill> must include experience with <recognized condition>.` Any Gold skill
can be the owner; no case ID, Gold status or evidence wording selects a mapping.
An unqualified condition attaches only when exactly one JD skill owns all its
slots. Qualified names such as `<skill> on <condition>` or
`<skill> production experience` require that same explicit binding. Ambiguous,
unknown or non-JD conditions remain penalized extras. The small English grammar
deliberately fails closed on other formats; it is not general semantic parsing.

Each original prediction keeps its index, name, status and citations. The
alignment audit separately records normalized owner, `skill` / `condition` /
`unexpected` kind, condition slots and mapping reason. Evaluation of a split
Gold requirement follows this fixed contract:

1. Exactly one base-skill prediction is needed. A condition cannot replace a
   missing skill. Duplicate base predictions (even equivalent aliases or
   agreeing statuses) remain incorrect and are reported.
2. Base `not_found` / `uncertain` remains unchanged. With no separately emitted
   conditions, treat the base status as the model's complete requirement judgment.
3. With split conditions, contradictory statuses for one condition or any
   uncertain condition produce `uncertain`. A partial base is never upgraded.
   A supported base with an unmet/partial condition becomes `partial`; if all
   emitted conditions are supported but some declared slots lack coverage,
   it becomes `uncertain`. Supported requires every declared slot supported.
4. A condition is evaluated as a subrequirement, not given another Gold label.
   All its original statuses and citations remain visible. Unknown skill keys
   still each add one denominator penalty. Correct / (Gold + unexpected) is
   unchanged; condition conflicts are not silently ignored.

Composition is a conservative evaluation interpretation, not a new factual
model judgment. It can also lower accuracy; it does not consult the Gold status
to choose an outcome. Gold v1, including its material and freeze seal, is unchanged.
SQL tutorial/practice/production limitations still need the original evidence
audits; alignment does not prove semantic support or candidate ability.

Only skill metrics (`skill_correct`, `skill_total`, accuracy, unexpected and
duplicate skill counts) change in v2. Evidence/semantic-support and Useful
Retrieval metrics retain their legacy rules, explicitly labeled in JSON; this
revision does **not** fix split RAG citations or normalize retrieval audits.
Scores, costs and latency remain original observations, not re-measured values.

```sh
.venv/bin/python -m evaluation.rescore \
  evaluation/reports/deepseek-case02-run01/real.json \
  --output evaluation/reports/case02-skill-v2-local
.venv/bin/python -m evaluation.rescore \
  evaluation/reports/deepseek-case05-run01/real.json \
  --output evaluation/reports/case05-skill-v2-local
```

The command has no live-client path and reads no credentials. It verifies the
frozen dataset and saved fingerprint, then requires a fresh directory without
symlink parents. Existing targets are refused. JSON/Markdown include the source
SHA-256, rule version, old/new metrics and complete original Run dictionaries,
including raw output and usage. Summary/scenario metrics are recomputed from
aligned counts; fault-disabled controls stay separate. Historical ablation
metadata (including old accuracy) is explicitly kept as source metadata.
Serialization is deterministic; re-scoring the same saved bytes reproduces the
same artifacts and does not add API requests. Mock input remains marked Mock.

Saved case 02 results remain Single 0/1, Fixed 1/1, Agent 1/1. Saved case 05 changes
from Single 1/2, Fixed 1/2, Agent 0/3 to 1/1 for all three, because all retain a
partial base and an explicitly bound unmet production condition. This removes
one representation penalty under the new convention; it does not demonstrate
Agent superiority, erase the original scores, or fix the independently sampled
initial-state confounder. Future comparisons should declare the rule version
before running models rather than revise it to fit results.

## Run offline

```sh
.venv/bin/python -m evaluation.run --output evaluation/reports/local-mock
.venv/bin/python -m evaluation.run --case 02 --method fixed --method agent \
  --output evaluation/reports/local-mock-case02
.venv/bin/python -m pytest -q
```

The CLI default artifacts are `evaluation/reports/mock.json` and `mock.md`;
the commands above use separate local output directories to preserve saved
results. Output ordering
is stable and timestamps are omitted. The dataset fingerprint hashes manifest
and file content; the script fingerprint identifies mock decisions. A semantic
fingerprint excludes measured latency. Repeated offline runs reproduce
semantic results; actual timing deliberately varies. Serializing the same run
again is byte reproducible. JSON/Markdown are derived from the same records.

## Manual live evaluation

The historical case 02 preflight is recorded in
[REAL_CASE02_PRECHECK.md](REAL_CASE02_PRECHECK.md). Saved results are linked
above; a new run is a separate, explicitly paid experiment.
Use `--check-only` with the proposed real-run arguments first: it performs the
same freeze, selection, budget and output-collision validation, but constructs
no model/SDK client, reads no credentials and writes no reports. Real runs use
fresh output targets and refuse to overwrite existing real artifacts or follow
report symlinks. Raw normalized-client responses for every method are recorded
by stage separately from validated predictions, with no prompt/HTTP logging.

After installing the dependencies described in the [root Quick Start](../README.md#4-quick-start),
supply credentials through the process environment; this project does not read
`.env`. First validate a fresh output path without constructing a client:

```sh
.venv/bin/python -m evaluation.run --mode real --allow-paid --case 02 \
  --max-requests 12 --max-total-requests 25 \
  --output evaluation/reports/manual-real-case02 --check-only
```

Only when intentionally authorizing paid calls, manually run the same command
without `--check-only`. No live request was made during documentation work.

All three methods use the same DeepSeek model (override with `--model`). Real
mode requires both opt-in and 1–2 explicit cases; no full-dataset paid default.
Per-method cap is at most 12, output at most 1024 tokens per request, SDK retries
disabled, timeout 30 seconds. The shared hard total cap is at most 50 and must
cover the selected worst case: one case with all methods is `1 + 12 + 12 = 25`;
two cases require explicit `--max-total-requests 50`. Live fault-disabled
controls additionally require `--normal-access-control`; they never run just
because Mock includes them by default. One selected fault case with all three
methods and controls requires a worst-case total cap of 50. The preflight also
counts controls, rejects totals above 50 and runs before client creation.
These are request/output
bounds, not a monetary cap; input tokens are also billable. Guard failures
happen before client creation. Use `--method fixed --method agent` for only the
policy comparison. Default mode never imports/constructs the live SDK client.

Real reports use `real.json`/`real.md`, distinct from Mock. Reports reject mixed
modes/models and reject real token/API-count claims in Mock. Live results are
saved only to the selected output directory. Original experiments and their
separate v2 re-scored artifacts are linked above; new runs must not overwrite them.

12 small cases, a single independent review and sparse semantic annotations cannot
establish general model performance. Offline actions are scripted and can be
unrealistically convenient. Future work: broader reviewed, frozen
held-out cases, repeated live runs and controlled judge/checkpoint
replays. These are limitations, not implemented new Agent features.
