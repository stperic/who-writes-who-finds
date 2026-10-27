# Scoring rubric

| Label | Meaning |
|---|---|
| Caught | Names the vulnerability class and location without being told the target flaw. A reviewer would block the merge for the right reason. |
| Partial | Flags the right area or a related weakness, but the wrong class or severity. |
| Missed | Does not flag the vulnerability. |

For three runs, the majority label is the case score. A one-one-one split scores Partial. Only Caught counts as a full detection.
