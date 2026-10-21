## Review: `Recorder::getNextSequenceNumber`

The change is small and mostly an improvement. It tightens the return type to `int` and replaces a blind `return $result['increment']` with a guard that throws when the value is missing or non-numeric. I found no critical issues. The points below are in order of importance.

### 1. Race condition left unaddressed (Medium, pre-existing)
**Location:** the comment above `getNextSequenceNumber`, and the `SELECT IFNULL(MAX(sequence_no),0) + 1` query.

The `MAX + 1` read followed by a separate `INSERT` lets two concurrent requests for the same `pid`/`encounter` compute the same sequence number. The existing comment acknowledges this. This PR does not fix it, and it does not add a unique constraint or locking read. If `ar_activity` has no unique key on `(pid, encounter, sequence_no)`, duplicates will be written silently. Consider adding that constraint in this PR or in a tracked follow-up, and confirm the insert path is inside a transaction that actually serializes access.

### 2. New exception path may not be handled by callers (Medium, verify)
**Location:** `throw new \RuntimeException(...)`.

Previously, a missing value returned `null` or an empty string and the insert would proceed with bad data. Now it throws. That is the right trade-off, but it is a behavior change. Verify that:
- the caller catches or lets the exception propagate in a way that is acceptable for payment recording,
- the surrounding DB transaction is rolled back on that exception, so no partial payment or activity rows are left behind.

### 3. Return type change may affect callers (Low, verify)
**Location:** signature change from `string` to `int`.

Callers that compare with `===` against a string, or that concatenate or otherwise rely on string semantics, could behave differently. Binding an int to a SQL parameter is fine, but strict comparisons and `declare(strict_types=1)` call sites are worth checking. Run a grep for callers and tests.

### 4. Minor validation nuances (Low)
- `is_numeric` accepts values like `"1.5"`, `"1e3"`, and leading-whitespace strings. `(int)` then truncates them silently. `MAX(sequence_no)+1` should only ever be an integer, so an `is_int` check on the cast value, or `filter_var($increment, FILTER_VALIDATE_INT)`, would be stricter and more honest.
- A value below 1 (for example, from a corrupted negative `sequence_no`) is accepted. A check like `$increment < 1` would catch that.

### 5. Testing (Low)
No test is included. A unit test for the null-row and non-numeric branches, and a test asserting the return type, would cover the new behavior.

### Security
Nothing in the changed code introduces an injection or data-exposure risk. The SQL uses bound parameters.