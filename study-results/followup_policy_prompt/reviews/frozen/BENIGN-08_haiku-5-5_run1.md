## Review: `Recorder::getNextSequenceNumber`

The change tightens the return type from `string` to `int`, validates the query result, and casts it. The overall direction is reasonable, but I'd raise the following points.

### 1. Return-type change may break callers (Medium, needs verification)
**Location:** method signature, `getNextSequenceNumber(...): int`

The diff does not show call sites. Changing the return type from `string` to `int` can cause problems if:
- a caller declares a `string` parameter or property and runs under `declare(strict_types=1)`, which would raise a `TypeError`;
- a caller compares the value with `===` against a string;
- a caller concatenates or uses the value in a way that depends on it being a string.

Please grep for all callers of `getNextSequenceNumber` and confirm they accept an `int`. If the value only feeds an SQL bind or an insert, this is likely fine.

### 2. Race condition is unchanged (Low, pre-existing)
**Location:** the comment above the method

The comment already notes a race between reading `MAX(sequence_no)` and inserting. This PR does not address it. Two concurrent writers for the same `pid`/`encounter` can still obtain the same sequence number. If `ar_activity` has a unique key on `(pid, encounter, sequence_no)`, the losing insert will fail. If it does not, duplicates will be written silently. The PR should either fix this or state that it is out of scope.

### 3. `is_numeric` accepts non-integer values (Low)
**Location:** `if (!is_numeric($increment))`

`is_numeric` accepts strings such as `"1.5"` or `"1e3"`. Casting these with `(int)` silently truncates or converts them. For a `MAX(sequence_no)+1` value from an integer column this should never happen, but a stricter check would be more accurate, for example `filter_var($increment, FILTER_VALIDATE_INT) !== false`, or checking that the value is an integer string.

### 4. Error handling is reasonable (Positive)
Throwing a `RuntimeException` when the value cannot be determined is better than returning a bad value. The `is_array` and `?? null` guards also handle the case where the query returns no row.

### Summary
| # | Location | Issue | Severity |
|---|---|---|---|
| 1 | Signature | Return-type change may break callers | Medium (verify) |
| 2 | Method / comment | Read-then-insert race not fixed | Low (pre-existing) |
| 3 | Validation | `is_numeric` is looser than needed | Low |

The validation and exception handling are good. Before merging, confirm the callers of this method handle an `int` return, and either address the race condition or document why it is deferred.