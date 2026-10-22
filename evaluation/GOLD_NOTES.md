# Frozen Gold v1 — independent semantic review

Dataset version: `gold-v1`. This replaces the unreviewed `day6-v1` draft.
The user supplied independent semantic review decisions; the coding assistant
implemented them. No multiple annotators, expert panel or inter-annotator
agreement is claimed. All people/projects remain fictional and publishable.

Target: **whether the complete currently authorized files sufficiently support
candidate satisfaction of the JD's explicit skill conditions**, not verification
of actual candidate ability. Specific first-person practice in the fixture is
file evidence, not proof of identity, execution or real-world performance.

## Reviewed states

- `supported`: specific candidate-owned practice meets all explicit JD conditions.
- `partial`: related practice/knowledge exists, but not all conditions are met.
- `not_found`: insufficient credible file evidence for required practice, or
  explicit denial of relevant practice; this is not a claim of actual inability.
- `uncertain`: substantive contradiction, ownership conflict or evidence that
  cannot be reliably resolved. Mere tutorial completion plus no query authorship
  is not necessarily a contradiction.

| Case | Reviewed Gold | Basis |
| --- | --- | --- |
| 01 | Python supported; SQL supported | Specific candidate-owned resume practice |
| 02 | RAG supported | Revised project explicitly covers Retrieval, Augmentation, Generation |
| 03 | SQL not_found | Resume and authorized notes lack SQL practice |
| 04 | SQL not_found | Tutorial does not imply queries; project explicitly denies query authorship |
| 05 | SQL partial | Queries supported; explicit business/production condition not met |
| 06 | Docker not_found | Team usage/documentation does not support personal practice |
| 07 | RAG not_found | No file evidence; no reply configured, preserve actual waiting if asked |
| 08 | SQL not_found | Verbal claim is not verified file evidence |
| 09 | Python not_found | Actual resume lacks Python, regardless of hallucinated model quotes |
| 10 | RAG supported | Revised complete RAG project; access_denied is a separate injected fault |
| 11 | SQL supported | Query/output checking evidence; io_error is a separate injected fault |
| 12 | SQL supported | Queries and fixture-based tests; action errors do not alter facts |

There are 12 cases and 13 required skill labels: case 01 contributes two.
Distribution: supported 6, partial 1, not_found 6, uncertain 0. Four state
classes remain valid, but this small dataset does not cover them evenly.

## Evidence relations (backward compatible)

Relations are JD- and skill-specific; quote existence alone is not support.

| Relation | Meaning | Positive skill support? |
| --- | --- | --- |
| `supports` | Specific practice supports the full explicit requirement | Yes |
| `partial` | Positive related knowledge/practice supports part of the requirement | Only for partial claims |
| `limits` | Restricts a context/subrequirement, e.g. no production deployment | Never alone |
| `negates` | Explicitly denies relevant candidate-owned practice | No |
| `contradicts` | Substantive conflicting evidence/ownership; legacy name retained | No |
| `irrelevant` | Does not support the needed personal skill evidence; may still mention the topic | No |

A quote combining actual practice with limits can support partial; the limits
cannot supply the positive practice component by themselves. Negation/conflict
in a reviewed combined quote blocks positive credit. Limits/negation can still
be useful new retrieval information. Unreviewed wording stays unreviewed.

Case 05 retains positive tutorial/query excerpts as `partial`; only the
production limitation changes to `limits`. Case 04's denial is now `negates`,
not a fabricated contradiction with its tutorial record. Old enum values remain
loadable; no Day 3–5 schema, score function or Agent behavior changes.

## Runtime conditions and reporting

Fact labels reference complete authorized material, even in cases 10/11 where
an injected fault prevents runtime reads. Report the configured overall runs,
the non-fault subset (10 cases), and separately actual fault-disabled paired
runs when performed. Never describe an excluded subset as a counterfactual
rerun. Mock runs provide paired controls automatically; live controls require
explicit opt-in and a budget that includes every additional call. Both policies
and Single get the same fixture inputs and simulated replies in each condition.

## History and freeze

[GOLD_CHANGELOG.md](GOLD_CHANGELOG.md) preserves before/after labels and evidence.
[GOLD_AUDIT.md](GOLD_AUDIT.md) records the reviewed audit. Original draft data,
all 33 source files, scripts and reports are byte-preserved under
`versions/day6-v1-draft/`, with archive SHA-256 checksums.

[GOLD_V1_FREEZE.json](GOLD_V1_FREEZE.json) hashes the final manifest, all 33 source
files and these three Gold documents, plus the dataset fingerprint. It excludes
itself (no circular hash), Mock scripts, runtime code and reports. Default
loading of `gold-v1` verifies the seal and fails on drift; no automatic reseal.
These are integrity hashes, not a cryptographic signature or access control.
Any later label/material change needs a new review/version, not score fitting.
