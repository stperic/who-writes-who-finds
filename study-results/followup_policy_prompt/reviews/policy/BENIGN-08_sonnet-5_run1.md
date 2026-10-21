## Review Comments

**File:** `src/PaymentProcessing/Recorder.php` — `getNextSequenceNumber()`

1. **Race condition still unaddressed** (Pre-existing, Medium/High)
   The comment directly above this method explicitly documents a known race condition in computing the next sequence number via `MAX(sequence_no)+1` without a locking read or atomic insert. This PR touches this exact method but only adds type-safety/validation — it does not fix (or even open a tracking issue for) the underlying concurrency bug. Since two concurrent transactions can read the same `MAX(sequence_no)` and both insert using the same `sequence_no`, this can produce duplicate sequence numbers for the same patient/encounter. Given this method is being modified anyway, it would be worth at minimum filing a follow-up ticket or adding a `SELECT ... FOR UPDATE` as the comment itself suggests.

2. **Return type change from `string` to `int` may affect callers** (Medium)
   The diff doesn't show any call sites being updated. If downstream code relies on the previous `string` return (e.g., strict comparisons `===`, string concatenation assumptions, or storage into a column typed as varchar with specific formatting such as zero-padding), changing to `int` could introduce subtle behavior differences. Worth verifying all call sites and any serialization/storage assumptions.

3. **Generic exception message lacks context** (Low)
   `throw new \RuntimeException('Could not determine next ar_activity sequence number');` doesn't include `$patientId` or `$encounterId`, which would be useful for diagnosing production issues when this fails. Consider including them in the message (watching for logging/PII concerns, though these are just internal IDs so likely fine).

4. **Silent truncation risk with `(int)` cast** (Low)
   `is_numeric()` accepts floats, decimals, and scientific notation strings (e.g., `"1.9"`, `"1e3"`). The subsequent `(int)` cast would silently truncate a non-integer numeric value rather than treating it as an error. Since this value seeds a sequence number, a stricter check (e.g., `ctype_digit` or verifying `(string)(int)$increment === (string)$increment`) would be safer than merely `is_numeric`.

5. **No test coverage added** (Low/Maintainability)
   The new validation branch (non-array result, missing key, non-numeric value) has no accompanying unit tests in the diff. Given this is defensive code for a concurrency-sensitive financial record (accounts receivable), test coverage for the failure path would improve confidence and prevent regressions.

Overall: the change itself is a reasonable, low-risk hardening of error handling, but it doesn't address the more serious, already-flagged race condition in the same method, and callers' compatibility with the new `int` return type should be verified.