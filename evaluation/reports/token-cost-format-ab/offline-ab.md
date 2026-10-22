# Token cost optimization — offline A/B

Fixed responses with current code/frozen fixtures validate format and controller equivalence, not live model behavior, historical HTTP prompt lengths or token savings.

Python len() of message.content summed over all action-decision requests; includes instruction, schema and data; not tokens or bytes.

Only JSON formatting whitespace outside string values changes.

| Fixture | Case | Decision calls before → after | Decision context characters before → after | All LLM requests | Retrieval attempts | Final status |
| --- | --- | --- | --- | --- | --- | --- |
| scripted_mock | 01 | 1 → 1 | 2784 → 2614 | 3 → 3 | 0 → 0 | finished |
| scripted_mock | 02 | 2 → 2 | 6115 → 5738 | 5 → 5 | 1 → 1 | finished |
| scripted_mock | 03 | 3 → 3 | 9074 → 8520 | 5 → 5 | 1 → 1 | finished |
| scripted_mock | 04 | 3 → 3 | 9043 → 8489 | 6 → 6 | 1 → 1 | finished |
| scripted_mock | 05 | 3 → 3 | 9049 → 8495 | 6 → 6 | 1 → 1 | finished |
| scripted_mock | 06 | 1 → 1 | 2623 → 2466 | 3 → 3 | 0 → 0 | finished |
| scripted_mock | 07 | 1 → 1 | 2707 → 2543 | 3 → 3 | 0 → 0 | waiting_for_user |
| scripted_mock | 08 | 2 → 2 | 5513 → 5187 | 4 → 4 | 0 → 0 | finished |
| scripted_mock | 09 | 1 → 1 | 2713 → 2549 | 3 → 3 | 0 → 0 | waiting_for_user |
| scripted_mock | 10 | 1 → 1 | 2884 → 2708 | 3 → 3 | 1 → 1 | permission_denied |
| scripted_mock | 11 | 1 → 1 | 2883 → 2707 | 3 → 3 | 1 → 1 | tool_error |
| scripted_mock | 12 | 3 → 3 | 8877 → 8337 | 6 → 6 | 1 → 1 | finished |
| saved_response_replay | 02 | 2 → 2 | 6115 → 5738 | 5 → 5 | 1 → 1 | finished |
| saved_response_replay | 05 | 4 → 4 | 13672 → 12837 | 7 → 7 | 2 → 2 | finished |

All equivalence checks passed: True

JSON retains per-call character counts, waiting/error counts, equivalence checks and source hashes. No historical API usage is attributed to the replay. Real token usage is unavailable; no token savings rate is estimated.
