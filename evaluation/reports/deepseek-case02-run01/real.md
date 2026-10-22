# Day 6 evaluation — real

Small live-model experiment; review provenance is recorded, no multiple-annotator agreement claimed

Model: `deepseek-flash`; dataset: `gold-v1`.

Initial fictional fixtures and labels drafted by coding assistant; independent semantic review decisions supplied by the user and implemented by coding assistant for frozen Gold v1. No multiple-annotator agreement is claimed. Target: sufficiency of complete authorized file evidence against explicit JD skill conditions, not verification of actual candidate ability.

Dataset fingerprint: `8b6061303cda37c88904cead19d77500f9e9ab6405ad7f993ffd1d3b7f46c105`

Semantic fingerprint (excluding measured latency): `b19d9f169d2f1575cf85e2d3fc601bac064b563c5b46e151df2e64a3e72d01e4`

Single sees only resume/JD and keeps raw, unverified judgments and model scores. Fixed and Agent share grants, semantic prompts, evidence validation, scoring and caps; only action selection changes. Fixed decisions do not count as LLM requests.

JSON model_outputs retains original normalized-client response text by stage for every method. initial_states and predictions are separate validated results for Fixed/Agent; Single remains unverified. No prompts, HTTP headers or raw SDK errors are recorded. execution_order gives actual method order.

| Method | Skill accuracy | Verbatim validity | Positive semantic support | Finished | Waiting | Error |
| --- | --- | --- | --- | --- | --- | --- |
| agent | 100.0% | 100.0% | unavailable | 100.0% | 0.0% | 0.0% |
| fixed | 100.0% | 100.0% | unavailable | 100.0% | 0.0% | 0.0% |
| single | 0.0% | 100.0% | unavailable | 100.0% | 0.0% | 0.0% |

Semantic support uses reviewed gold excerpts only; unknown wording remains unreviewed. Verbatim validity does not prove relevance or ownership. No citations means unavailable, not 100%.

| Method | Useful / attempts | LLM requests | API attempts | Tokens | Seconds | Invalid / duplicate |
| --- | --- | --- | --- | --- | --- | --- |
| agent | 1 / 1 | 5 | 5 | 4488 | 8.963863 | 0 / 0 |
| fixed | 1 / 2 | 3 | 3 | 2125 | 6.772719 | 0 / 0 |
| single | 0 / 0 | 1 | 1 | 587 | 4.041731 | 0 / 0 |

## Runtime faults versus normal access

Overall above retains configured faults. The non-fault subset excludes fault cases for all methods; it is not a counterfactual rerun. Controls below are actual paired runs with only the injected fault disabled. Gold, files, grants, policies and caps stay the same. Live LLM sampling can still differ.

| Condition | Method | Runs | Skill accuracy | Finished / waiting / errors | Requests |
| --- | --- | --- | --- | --- | --- |
| non-fault subset | agent | 1 | 100.0% | 1 / 0 / 0 | 5 |
| non-fault subset | fixed | 1 | 100.0% | 1 / 0 / 0 | 3 |
| non-fault subset | single | 1 | 0.0% | 1 / 0 / 0 | 1 |
| all cases, fault-disabled replacements | agent | 1 | 100.0% | 1 / 0 / 0 | 5 |
| all cases, fault-disabled replacements | fixed | 1 | 100.0% | 1 / 0 / 0 | 3 |
| all cases, fault-disabled replacements | single | 1 | 0.0% | 1 / 0 / 0 | 1 |

Actual execution requests including controls: agent=5, fixed=3, single=1.

## Scenario groups

| Scenario | Method | Skill accuracy | Finished / waiting / errors | Useful / attempts | Requests |
| --- | --- | --- | --- | --- | --- |
| supplement_available | agent | 100.0% | 1 / 0 / 0 | 1 / 1 | 5 |
| supplement_available | fixed | 100.0% | 1 / 0 / 0 | 1 / 2 | 3 |
| supplement_available | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |

## Policy ablation and limitations

| Case | Same inputs / grants / caps | Same initial checkpoint | Fixed / Agent accuracy | Fixed / Agent retrievals | Fixed / Agent requests |
| --- | --- | --- | --- | --- | --- |
| 02 | True | True | 100.0% / 100.0% | 2 / 1 | 3 / 5 |

This is a capability-controlled policy comparison: identical production executor, judge prompts, scorer and authorized inputs. JSON includes per-case comparability and initial-state checks. Live calls are independently sampled; different initial judgments/reviews are confounders, so do not interpret a difference as a causal autonomy benefit. Actual file counts are reported.

Mock answers/actions are predefined, including deliberate errors. They establish no superiority of Agent or Workflow. A finished run may be factually wrong; waiting is separate from failure. Small reviewed fixtures, partial semantic annotation and no multiple-annotator agreement limit generalization.

Request counts include failed LLM attempts; API attempts and usage are provider-observed only. Tokens are unavailable if any call lacks usage; none are estimated. Latency is measured locally, and mock timing says nothing about live API performance. JSON retains raw Single output, predictions, traces, interactions, budgets and evidence/retrieval audits.
