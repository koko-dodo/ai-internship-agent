# Case 02 DeepSeek preflight — offline inspection only

This preparation did not contact DeepSeek, inspect credentials, read `.env`,
change frozen Gold, or overwrite saved evaluation results. SDK-boundary tests
use an offline SDK stub; their outputs are not live-model measurements.

## Verified inputs and real-client path

- Dataset: `gold-v1`; fingerprint
  `8b6061303cda37c88904cead19d77500f9e9ab6405ad7f993ffd1d3b7f46c105`.
- Case `02`: `evaluation/02/resume.md` and `evaluation/02/jd.md` relative to
  `examples/`. JD remains `Required: RAG.`; one Gold skill, `RAG supported`.
- Both multi-step methods receive the same grants: `a_notes.md` and `b_rag.md`.
  The latter explicitly describes Retrieval, Augmentation and Generation.
  Single receives the same resume/JD, without supplemental text or tools.
- Freeze verification occurs at suite validation, before and after each real
  method. Do not edit input files during the run. These checks detect drift;
  they are not an OS-level atomic snapshot against concurrent hostile edits.
- CLI real mode constructs `DeepSeekLLMClient` with the OpenAI-compatible SDK
  at `https://api.deepseek.com`. Only future opted-in execution reads
  `DEEPSEEK_API_KEY` from the process environment. No dotenv loading or Fake
  fallback exists. Missing credentials/configuration abort client creation.
- Dependency-injected real clients must also be the configured concrete
  DeepSeek adapter with SDK usage observation, matching model, call cap,
  1024 output-token cap and 30-second timeout; a generic Fake cannot be labeled
  real. Tests intentionally inject a stub at the SDK boundary to verify wiring.

## Method order, budgets, and expected paths

Order is sequential **single → fixed → agent** by default, or the explicit
repeated `--method` order. Each gets a fresh client with the same selected
DeepSeek model. The report records `execution_order` and `request_plan`.
Alphabetically sorted summary tables are not execution order.

| Method | Request cap | Typical successful Case 02 path, if RAG is extracted correctly |
| --- | --- | --- |
| Single | 1 | One resume/JD assessment: 1 call |
| Fixed | 12 | JD extraction + resume assessment + supplemental review: 3 calls |
| Agent | 12 | Same two initial calls + SEARCH + supplemental review + FINISH: 5 calls; 6 if it searches the empty notes first |

Typical combined path: **9–10 calls**, not a promise or a measured bill.
On successful but different decisions: Fixed can stop after two calls if its
initial judgment is supported; Agent can ASK_USER/FINISH after its third call.
Correctly extracted single-skill RAG allows at most one relevant supplemental
review across the two files; five decision rounds give an Agent path up to
8 calls. Mis-extracted skills, malformed responses, failures and recovery can
change these paths; use the enforced caps rather than this conditional estimate.
With the shared defaults, Fixed has at most two initialization calls plus three
supplemental reviews; Agent has at most two initialization calls, five decisions
and three reviews before any user resume. Case 02 has no reply and cannot resume.

The global reservation/cap is **1 + 12 + 12 = 25 attempts**. Preflight requires
the total to cover this reservation, even though structural paths can stop
earlier. LLM decisions count for Agent; fixed Python policy outputs do not.
Both multi-step methods keep 3 searches, 5 initial rounds and the existing
one-time 2-round resume window. No normal-access extra control runs are needed
for Case 02, which has no injected fault.

Failed model-interface calls consume the shared and per-method budgets. The
adapter counts SDK request attempts before dispatch, including API failures.
Local preparation failures can consume an interface attempt without sending
an API request; the two counters are separate. Client-construction failures
do not send a request. SDK automatic retries remain disabled.

These are request and output bounds, **not currency limits**. Prompt/input
tokens are also billable. Timeouts or missing usage must not be interpreted as
free calls. Price, account balance, network connectivity and server acceptance
have not been checked here. Smaller call counts can reflect premature FINISH
or wrong judgments; they do not alone demonstrate efficiency.

## User interaction and fairness

Case 02 has `user_reply=null`. If either multi-step method asks a question,
the report keeps the question/context and `waiting_for_user`; no answer is
invented, no verified evidence is created and no automatic resume occurs.
The CLI does not enter an interactive prompt or accept an ad-hoc reply for
this evaluation. Waiting is distinct from both finished and failed.

Fixed/Agent retain identical semantic prompts, executor, evidence guards,
scorer, grants and caps; only action selection differs. Their initial/review
model calls are independently sampled. Compare initial checkpoint fingerprints
and raw judgments before attributing a difference to policy. Fixed-first order
and provider caching/load can affect latency/cost, and one case cannot establish
statistical model performance. Single has a deliberately weaker information set.

## Report fields and output safety

- `raw_model_output`: original Single text/optional model score retained;
  Single predictions remain unverified by that method.
- `model_outputs`: original normalized-client responses for all methods, with
  request number and stage (`jd_extraction`, `initial_assessment`,
  `supplemental_assessment`, `action_decision`, `single_assessment`), usage when
  available, or a sanitized error marker. The adapter may reject malformed SDK
  responses before normalized text exists; raw HTTP payloads are not recorded.
- `initial_states` / `predictions`: separately validated multi-step states;
  `predictions[].citations` includes source, original text and located line/hash
  fields. `changes`, sanitized `trace` and metric audits remain separate.
- `cost.llm_requests`: interface attempts, including failures;
  `cost.api_requests`: adapter SDK attempts; `token_usage`: actual observed
  prompt/completion/total tokens. Missing usage on any call makes aggregate
  usage unavailable; `usage_requests_available` retains coverage. No estimates
  are substituted. Model outputs may quote fictional inputs intentionally;
  prompts, auth headers and raw SDK exceptions are not report fields.

Use a fresh output directory. Real files are named `real.json`/`real.md`, never
`mock.json`/`mock.md`. Existing real artifacts, symlink destinations and invalid
output directories are rejected before client creation; real writes use
exclusive creation to prevent later collisions. Runtime filesystem failures
can still prevent a report write, so do not run concurrently into one folder.
No evaluation writer reseals or updates frozen files. A CLI exit code of zero
means report generation succeeded, not that all three tasks or judgments did.

## Checked offline command

Run from the project root. This exact check-only command was executed without
constructing a client, accessing credentials, creating the output directory or
writing a report:

```sh
.venv/bin/python -m evaluation.run \
  --mode real --allow-paid --case 02 \
  --method single --method fixed --method agent \
  --model deepseek-flash --max-requests 12 --max-total-requests 25 \
  --output evaluation/reports/deepseek-case02-run01 --check-only
```

For a future intentional paid run, ensure the process environment already has
the key, keep these arguments and remove only `--check-only`. If that output
directory already contains real results, choose a new directory and rerun the
check. This preparation does not authorize or execute that paid run.
