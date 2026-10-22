# Day 6 evaluation — mock

SCRIPTED FRAMEWORK VALIDATION ONLY; not real model accuracy

Model: `scripted-fixture-v1`; dataset: `gold-v1`.

Initial fictional fixtures and labels drafted by coding assistant; independent semantic review decisions supplied by the user and implemented by coding assistant for frozen Gold v1. No multiple-annotator agreement is claimed. Target: sufficiency of complete authorized file evidence against explicit JD skill conditions, not verification of actual candidate ability.

Dataset fingerprint: `8b6061303cda37c88904cead19d77500f9e9ab6405ad7f993ffd1d3b7f46c105`

Semantic fingerprint (excluding measured latency): `c3decb3faa5ffae4d169adbd036cc9df1bfce372b0431bea6b5b9964b3bbd100`

Single sees only resume/JD and keeps raw, unverified judgments and model scores. Fixed and Agent share grants, semantic prompts, evidence validation, scoring and caps; only action selection changes. Fixed decisions do not count as LLM requests.

| Method | Skill accuracy | Verbatim validity | Positive semantic support | Finished | Waiting | Error |
| --- | --- | --- | --- | --- | --- | --- |
| agent | 61.5% | 100.0% | 75.0% | 66.7% | 16.7% | 16.7% |
| fixed | 61.5% | 100.0% | 75.0% | 66.7% | 16.7% | 16.7% |
| single | 46.2% | 83.3% | 80.0% | 100.0% | 0.0% | 0.0% |

Semantic support uses reviewed gold excerpts only; unknown wording remains unreviewed. Verbatim validity does not prove relevance or ownership. No citations means unavailable, not 100%.

| Method | Useful / attempts | LLM requests | API attempts | Tokens | Seconds | Invalid / duplicate |
| --- | --- | --- | --- | --- | --- | --- |
| agent | 4 / 7 | 50 | unavailable | unavailable | 0.029573 | 1 / 0 |
| fixed | 4 / 8 | 28 | unavailable | unavailable | 0.037094 | 0 / 0 |
| single | 0 / 0 | 12 | unavailable | unavailable | 0.011597 | 0 / 0 |

## Runtime faults versus normal access

Overall above retains configured faults. The non-fault subset excludes fault cases for all methods; it is not a counterfactual rerun. Controls below are actual paired runs with only the injected fault disabled. Gold, files, grants, policies and caps stay the same. Live LLM sampling can still differ.

| Condition | Method | Runs | Skill accuracy | Finished / waiting / errors | Requests |
| --- | --- | --- | --- | --- | --- |
| non-fault subset | agent | 10 | 72.7% | 8 / 2 / 0 | 44 |
| non-fault subset | fixed | 10 | 72.7% | 8 / 2 / 0 | 24 |
| non-fault subset | single | 10 | 54.5% | 10 / 0 / 0 | 10 |
| fault-disabled controls | agent | 2 | 100.0% | 2 / 0 / 0 | 10 |
| fault-disabled controls | fixed | 2 | 100.0% | 2 / 0 / 0 | 6 |
| fault-disabled controls | single | 2 | 0.0% | 2 / 0 / 0 | 2 |
| all cases, fault-disabled replacements | agent | 12 | 76.9% | 10 / 2 / 0 | 54 |
| all cases, fault-disabled replacements | fixed | 12 | 76.9% | 10 / 2 / 0 | 30 |
| all cases, fault-disabled replacements | single | 12 | 46.2% | 12 / 0 / 0 | 12 |

Actual execution requests including controls: agent=60, fixed=34, single=14.

## Scenario groups

| Scenario | Method | Skill accuracy | Finished / waiting / errors | Useful / attempts | Requests |
| --- | --- | --- | --- | --- | --- |
| complete | agent | 100.0% | 1 / 0 / 0 | 0 / 0 | 3 |
| complete | fixed | 100.0% | 1 / 0 / 0 | 0 / 0 | 2 |
| complete | single | 100.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| empty_retrieval | agent | 100.0% | 1 / 0 / 0 | 0 / 1 | 5 |
| empty_retrieval | fixed | 100.0% | 1 / 0 / 0 | 0 / 1 | 2 |
| empty_retrieval | single | 100.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| fabricated_citation | agent | 0.0% | 0 / 1 / 0 | 0 / 0 | 3 |
| fabricated_citation | fixed | 0.0% | 0 / 1 / 0 | 0 / 0 | 2 |
| fabricated_citation | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| invalid_action | agent | 100.0% | 1 / 0 / 0 | 1 / 1 | 6 |
| invalid_action | fixed | 100.0% | 1 / 0 / 0 | 1 / 1 | 3 |
| invalid_action | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| irrelevant_keyword | agent | 0.0% | 1 / 0 / 0 | 0 / 0 | 3 |
| irrelevant_keyword | fixed | 0.0% | 1 / 0 / 0 | 0 / 0 | 2 |
| irrelevant_keyword | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| negation | agent | 0.0% | 1 / 0 / 0 | 1 / 1 | 6 |
| negation | fixed | 0.0% | 1 / 0 / 0 | 1 / 1 | 3 |
| negation | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| partial_requirement | agent | 100.0% | 1 / 0 / 0 | 1 / 1 | 6 |
| partial_requirement | fixed | 100.0% | 1 / 0 / 0 | 1 / 1 | 3 |
| partial_requirement | single | 100.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| permission_failure | agent | 0.0% | 0 / 0 / 1 | 0 / 1 | 3 |
| permission_failure | fixed | 0.0% | 0 / 0 / 1 | 0 / 1 | 2 |
| permission_failure | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| supplement_available | agent | 100.0% | 1 / 0 / 0 | 1 / 1 | 5 |
| supplement_available | fixed | 100.0% | 1 / 0 / 0 | 1 / 2 | 3 |
| supplement_available | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| tool_failure | agent | 0.0% | 0 / 0 / 1 | 0 / 1 | 3 |
| tool_failure | fixed | 0.0% | 0 / 0 / 1 | 0 / 1 | 2 |
| tool_failure | single | 0.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| unverified_reply | agent | 100.0% | 1 / 0 / 0 | 0 / 0 | 4 |
| unverified_reply | fixed | 100.0% | 1 / 0 / 0 | 0 / 0 | 2 |
| unverified_reply | single | 100.0% | 1 / 0 / 0 | 0 / 0 | 1 |
| waiting_user | agent | 100.0% | 0 / 1 / 0 | 0 / 0 | 3 |
| waiting_user | fixed | 100.0% | 0 / 1 / 0 | 0 / 0 | 2 |
| waiting_user | single | 100.0% | 1 / 0 / 0 | 0 / 0 | 1 |

## Policy ablation and limitations

| Case | Same inputs / grants / caps | Same initial checkpoint | Fixed / Agent accuracy | Fixed / Agent retrievals | Fixed / Agent requests |
| --- | --- | --- | --- | --- | --- |
| 01 | True | True | 100.0% / 100.0% | 0 / 0 | 2 / 3 |
| 02 | True | True | 100.0% / 100.0% | 2 / 1 | 3 / 5 |
| 03 | True | True | 100.0% / 100.0% | 1 / 1 | 2 / 5 |
| 04 | True | True | 0.0% / 0.0% | 1 / 1 | 3 / 6 |
| 05 | True | True | 100.0% / 100.0% | 1 / 1 | 3 / 6 |
| 06 | True | True | 0.0% / 0.0% | 0 / 0 | 2 / 3 |
| 07 | True | True | 100.0% / 100.0% | 0 / 0 | 2 / 3 |
| 08 | True | True | 100.0% / 100.0% | 0 / 0 | 2 / 4 |
| 09 | True | True | 0.0% / 0.0% | 0 / 0 | 2 / 3 |
| 10 | True | True | 0.0% / 0.0% | 1 / 1 | 2 / 3 |
| 11 | True | True | 0.0% / 0.0% | 1 / 1 | 2 / 3 |
| 12 | True | True | 100.0% / 100.0% | 1 / 1 | 3 / 6 |

This is a capability-controlled policy comparison: identical production executor, judge prompts, scorer and authorized inputs. JSON includes per-case comparability and initial-state checks. Live calls are independently sampled; different initial judgments/reviews are confounders, so do not interpret a difference as a causal autonomy benefit. Actual file counts are reported.

Mock answers/actions are predefined, including deliberate errors. They establish no superiority of Agent or Workflow. A finished run may be factually wrong; waiting is separate from failure. Small reviewed fixtures, partial semantic annotation and no multiple-annotator agreement limit generalization.

Request counts include failed LLM attempts; API attempts and usage are provider-observed only. Tokens are unavailable if any call lacks usage; none are estimated. Latency is measured locally, and mock timing says nothing about live API performance. JSON retains raw Single output, predictions, traces, interactions, budgets and evidence/retrieval audits.
