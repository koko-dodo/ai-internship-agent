# Saved-run re-score — skill-alignment-v2

Mode: `real`; model: `deepseek-flash`; Gold: `gold-v1`.

Small live-model experiment; review provenance is recorded, no multiple-annotator agreement claimed

Only skill-status alignment/composition changes; evidence/retrieval metrics retain legacy rules. Model scores, outputs, verified flags, usage and latency are original observations.

Source SHA-256: `d1dbddffec56a204d8b5350073f7d48cd098aaf33721320f746b28c02e1aaf4c`

No API calls or new model judgments. This is a post-hoc protocol revision, not an independent replication.

| Case | Method | Original correct / total | Aligned correct / total | Original / aligned accuracy |
| --- | --- | --- | --- | --- |
| 02 | single | 0/1 | 0/1 | 0.0 / 0.0 |
| 02 | fixed | 1/1 | 1/1 | 1.0 / 1.0 |
| 02 | agent | 1/1 | 1/1 | 1.0 / 1.0 |

## Alignment trace

### Case 02 / single

```json
{
  "judgments": [
    {
      "condition_indices": [],
      "primary_indices": [
        0
      ],
      "reason": "conservative_condition_composition",
      "required_conditions": [],
      "skill": "RAG",
      "status": "not_found"
    }
  ],
  "mappings": [
    {
      "conditions": [],
      "index": 0,
      "key": "rag",
      "kind": "skill",
      "normalized_skill": "RAG",
      "original_skill": "RAG",
      "reason": "exact_name",
      "status": "not_found"
    }
  ],
  "unexpected_keys": []
}
```

### Case 02 / fixed

```json
{
  "judgments": [
    {
      "condition_indices": [],
      "primary_indices": [
        0
      ],
      "reason": "conservative_condition_composition",
      "required_conditions": [],
      "skill": "RAG",
      "status": "supported"
    }
  ],
  "mappings": [
    {
      "conditions": [],
      "index": 0,
      "key": "rag",
      "kind": "skill",
      "normalized_skill": "RAG",
      "original_skill": "RAG",
      "reason": "exact_name",
      "status": "supported"
    }
  ],
  "unexpected_keys": []
}
```

### Case 02 / agent

```json
{
  "judgments": [
    {
      "condition_indices": [],
      "primary_indices": [
        0
      ],
      "reason": "conservative_condition_composition",
      "required_conditions": [],
      "skill": "RAG",
      "status": "supported"
    }
  ],
  "mappings": [
    {
      "conditions": [],
      "index": 0,
      "key": "rag",
      "kind": "skill",
      "normalized_skill": "RAG",
      "original_skill": "RAG",
      "reason": "exact_name",
      "status": "supported"
    }
  ],
  "unexpected_keys": []
}
```

Condition-only claims cannot replace a missing base skill. Unknown names still add denominator penalties. Identical or conflicting duplicate base claims are not silently merged. Condition states are retained; conservative composition never upgrades the base status. Evidence/Useful Retrieval metrics have NOT been normalized by this revision. Fault-disabled controls, if present, stay separate in JSON. Original policy-ablation metadata is historical, including its old accuracies, and is not a new policy experiment.
