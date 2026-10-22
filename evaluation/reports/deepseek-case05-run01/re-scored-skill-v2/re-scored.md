# Saved-run re-score — skill-alignment-v2

Mode: `real`; model: `deepseek-flash`; Gold: `gold-v1`.

Small live-model experiment; review provenance is recorded, no multiple-annotator agreement claimed

Only skill-status alignment/composition changes; evidence/retrieval metrics retain legacy rules. Model scores, outputs, verified flags, usage and latency are original observations.

Source SHA-256: `016bee38d19d7a48d3051a35cc96a795455d00b29041385fe183c018dcac296f`

No API calls or new model judgments. This is a post-hoc protocol revision, not an independent replication.

| Case | Method | Original correct / total | Aligned correct / total | Original / aligned accuracy |
| --- | --- | --- | --- | --- |
| 05 | single | 1/2 | 1/1 | 0.5 / 1.0 |
| 05 | fixed | 1/2 | 1/1 | 0.5 / 1.0 |
| 05 | agent | 0/3 | 1/1 | 0.0 / 1.0 |

## Alignment trace

### Case 05 / single

```json
{
  "judgments": [
    {
      "condition_indices": [
        1
      ],
      "primary_indices": [
        0
      ],
      "reason": "conservative_condition_composition",
      "required_conditions": [
        "production",
        "real_business_data"
      ],
      "skill": "SQL",
      "status": "partial"
    }
  ],
  "mappings": [
    {
      "conditions": [],
      "index": 0,
      "key": "sql",
      "kind": "skill",
      "normalized_skill": "SQL",
      "original_skill": "SQL",
      "reason": "exact_name",
      "status": "partial"
    },
    {
      "conditions": [
        "real_business_data",
        "production"
      ],
      "index": 1,
      "key": "sql",
      "kind": "condition",
      "normalized_skill": "SQL",
      "original_skill": "Experience with real business data in production",
      "reason": "declared_condition_and_explicit_JD_binding",
      "status": "not_found"
    }
  ],
  "unexpected_keys": []
}
```

### Case 05 / fixed

```json
{
  "judgments": [
    {
      "condition_indices": [
        1
      ],
      "primary_indices": [
        0
      ],
      "reason": "conservative_condition_composition",
      "required_conditions": [
        "production",
        "real_business_data"
      ],
      "skill": "SQL",
      "status": "partial"
    }
  ],
  "mappings": [
    {
      "conditions": [],
      "index": 0,
      "key": "sql",
      "kind": "skill",
      "normalized_skill": "SQL",
      "original_skill": "SQL",
      "reason": "exact_name",
      "status": "partial"
    },
    {
      "conditions": [
        "real_business_data",
        "production"
      ],
      "index": 1,
      "key": "sql",
      "kind": "condition",
      "normalized_skill": "SQL",
      "original_skill": "SQL querying on real business data in production",
      "reason": "declared_condition_and_explicit_JD_binding",
      "status": "not_found"
    }
  ],
  "unexpected_keys": []
}
```

### Case 05 / agent

```json
{
  "judgments": [
    {
      "condition_indices": [
        1
      ],
      "primary_indices": [
        0
      ],
      "reason": "conservative_condition_composition",
      "required_conditions": [
        "production",
        "real_business_data"
      ],
      "skill": "SQL",
      "status": "partial"
    }
  ],
  "mappings": [
    {
      "conditions": [],
      "index": 0,
      "key": "sql",
      "kind": "skill",
      "normalized_skill": "SQL",
      "original_skill": "SQL querying",
      "reason": "declared_full_name_alias",
      "status": "partial"
    },
    {
      "conditions": [
        "real_business_data",
        "production"
      ],
      "index": 1,
      "key": "sql",
      "kind": "condition",
      "normalized_skill": "SQL",
      "original_skill": "real business data in production",
      "reason": "declared_condition_and_explicit_JD_binding",
      "status": "not_found"
    }
  ],
  "unexpected_keys": []
}
```

Condition-only claims cannot replace a missing base skill. Unknown names still add denominator penalties. Identical or conflicting duplicate base claims are not silently merged. Condition states are retained; conservative composition never upgrades the base status. Evidence/Useful Retrieval metrics have NOT been normalized by this revision. Fault-disabled controls, if present, stay separate in JSON. Original policy-ablation metadata is historical, including its old accuracies, and is not a new policy experiment.
