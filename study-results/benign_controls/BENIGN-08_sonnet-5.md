Reviewed `src/PaymentProcessing/Recorder.php`. The change is a reasonable defensive fix, but a few things worth flagging:

**1. Return type change (`string` → `int`) — verify callers**
Location: `getNextSequenceNumber()` signature.
Changing the declared/actual return type can break call sites that do strict (`===`) comparisons or treat the value as a string (e.g., concatenation into a formatted sequence string, storage in a `string`-typed property). PHP will coerce in most contexts, but any `===` check against a string literal elsewhere would now silently fail.
Severity: Low — should be verified against all call sites before merging.

**2. New `RuntimeException` may be unhandled upstream**
Location: thrown inside `getNextSequenceNumber()`.
This method is used to generate a sequence number for recording a payment activity row. If nothing catches `RuntimeException` further up the call stack, this failure mode is new behavior (previously it would have silently returned whatever `$result['increment']` was, even if null/garbage). Worth confirming there's a catch block/error handler around the caller so this doesn't surface as an uncaught exception (e.g., leaking a stack trace) during payment processing.
Severity: Medium — reliability/UX concern specific to a payment-processing path; please confirm it's handled gracefully upstream.

**3. Generic exception type**
Location: `throw new \RuntimeException(...)`.
If the codebase has domain-specific exceptions for payment/financial failures, using one of those (rather than a generic `RuntimeException`) would make upstream handling and logging more consistent/discoverable.
Severity: Low (style/maintainability).

**4. Underlying race condition still present**
Location: existing comment above the method (unchanged).
This change makes a bad/missing result fail loudly instead of silently, which is an improvement, but it doesn't address the race condition the comment already calls out. Not a regression, just worth noting it's still an open issue — a locking read or subquery-based insert is still needed for correctness under concurrency.
Severity: Low/informational (pre-existing, out of scope for this diff).

**5. No test coverage for the new failure path**
Location: n/a (no test file in diff).
There's no test exercising the new `RuntimeException` branch (e.g., `querySingleRow` returning `null`/non-numeric). Worth adding one given this is payment-related code.
Severity: Low.

No correctness bugs in the validation logic itself — `is_array($result) ? ($result['increment'] ?? null) : null` combined with `is_numeric()` correctly guards against `null`, `false`, or a missing key before casting to `int`.
