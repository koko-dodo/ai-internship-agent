# Frozen gold annotation notes — day6-v1

These 12 small cases, people and project descriptions are entirely fictional and
may be published with this repository. `cases.json` was authored before the
evaluation adapters, including statuses, rationales, exact quotes and line spans.
Labels are explicit developer annotations drafted by the coding assistant,
not outputs of the evaluated clients. They have not received independent human
review and must not be presented as a human-validated benchmark. Treat them as
proposed gold for framework validation until reviewed. Do not revise labels to
improve a model's score.

The reference is the **complete resume plus explicitly authorized material** and
the actual JD, rather than only what a particular run happened to retrieve.
Runtime access/I/O failure does not change factual gold labels. Resume-only
Single LLM therefore has an explicitly smaller information set.

| Case | Scenario | Gold and annotation basis |
| --- | --- | --- |
| 01 | Complete resume | Python and SQL supported by specific candidate-owned work |
| 02 | Missing RAG in resume | RAG supported in b_rag.md; a_notes.md is a distractor |
| 03 | Empty retrieval | SQL not_found throughout authorized material |
| 04 | Negation | SQL uncertain: tutorial plus explicit denial of query authorship |
| 05 | Partial subrequirements | SQL partial: actual queries, synthetic data, no required production experience |
| 06 | Irrelevant keyword | Docker not_found: team usage is not candidate practice |
| 07 | Clarification pending | RAG not_found; no simulated reply, preserve waiting_for_user |
| 08 | Unverified user claim | SQL not_found; reply supplies no verified project evidence |
| 09 | Fabricated model quote | Python not_found in actual files, regardless of a hallucinated citation |
| 10 | Permission failure | RAG factually supported in authorized file; shared injected access denial |
| 11 | Tool failure | SQL factually supported; shared injected I/O error |
| 12 | Illegal action | SQL supported in project; scripted invalid Agent action tests recovery only |

Evidence relations (`supports`, `partial`, `contradicts`, `irrelevant`) are
**skill- and JD-specific**, not keyword labels. Gold records define reviewed
excerpts, not an exhaustive list of every possible wording. A verbatim quote
outside a reviewed excerpt is marked semantically **unreviewed**, not assumed
false. Missing evidence for not_found is deliberate. Simulated replies are
unverified statements and cannot become file evidence or change the gold.

Keep offline mock scripts separate from labels. They deliberately include wrong
judgments and invented quotes; they verify instrumentation, not model quality.
For future benchmark changes, create a new dataset version and record a manual
review before running models. Formal annotation agreement is future work.
