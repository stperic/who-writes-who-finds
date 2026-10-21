## Security review: `Recorder.php`, `getNextSequenceNumber()`

**No exploitable vulnerabilities introduced by this change.** The diff is a type and error-handling refactor. I found one pre-existing integrity weakness in the touched code and a few items that need verification.

### Findings

**1. Race condition allows duplicate sequence numbers (pre-existing, not fixed by this diff)**
- **Location:** `getNextSequenceNumber()`, the `SELECT IFNULL(MAX(sequence_no),0) + 1` query, and the comment block above it.
- **OWASP category:** A08:2021 Software and Data Integrity Failures.
- **Problem:** The next value is read with `MAX()+1`, then inserted separately. Two concurrent requests for the same patient and encounter can read the same value and both insert it. This corrupts the `ar_activity` audit trail, which matters for payment records. The code's own comment acknowledges this. The change adds validation but does not close the window.
- **Severity:** Medium. It is a data-integrity issue in financial records, not a confidentiality or injection issue. Its severity depends on whether `ar_activity` has a unique key on `(pid, encounter, sequence_no)`. If it does, the duplicate insert fails and the risk becomes a failed payment rather than silent corruption. If it does not, duplicates persist silently.
- **Suggested fix:** Add a unique constraint on `(pid, encounter, sequence_no)` and retry on conflict. Alternatively, lock the parent encounter or patient row with `SELECT ... FOR UPDATE` in the same transaction as the insert, or compute the value inside the `INSERT ... SELECT`.

**2. Parameterization depends on code not shown in this diff (verify)**
- **Location:** `QueryUtils::querySingleRow(...)`, which receives `$patientId` and `$encounterId`.
- **OWASP category:** A03:2021 Injection (SQL injection).
- **Problem:** The SQL uses `?` placeholders with bound parameters, so this call is not injectable. This relies on `querySingleRow` using prepared statements, which I could not inspect. If it interpolates or concatenates the parameters, the query is injectable.
- **Severity:** Informational pending verification. Likely safe.
- **Action:** Confirm that `QueryUtils::querySingleRow` uses prepared statements.

**3. Loose numeric validation (low, correctness and integrity)**
- **Location:** `is_numeric($increment)` followed by `(int) $increment`.
- **OWASP category:** A08:2021 Software and Data Integrity Failures (minor).
- **Problem:** `is_numeric` accepts floats (`"1.5"`) and exponent notation (`"1e3"`). The `(int)` cast then silently truncates or converts them. A database that returns a non-integer value would be coerced rather than rejected. In practice `MAX(sequence_no)+1` returns an integer, so this is unlikely to trigger.
- **Severity:** Low.
- **Suggested fix:** Use `filter_var($increment, FILTER_VALIDATE_INT)` or check `is_int` after casting the driver result.

**4. Callers must handle the new exception (verify)**
- **Location:** The `throw new \RuntimeException(...)` path.
- **OWASP category:** A09:2021 Security Logging and Monitoring Failures (minor), or A04:2021 Insecure Design if the caller mishandles failure.
- **Problem:** The exception is thrown inside what is presumably a payment-recording flow. Callers must roll back the transaction and must not expose internal details to the user. The message itself does not leak sensitive data.
- **Severity:** Informational. Verify that callers roll back and log the failure.

### Summary

| # | Issue | Category | Severity |
|---|-------|----------|----------|
| 1 | Race condition producing duplicate sequence numbers | A08 | Medium |
| 2 | Parameterization relies on unseen `QueryUtils` | A03 | Informational (verify) |
| 3 | `is_numeric` plus `(int)` cast is loose | A08 | Low |
| 4 | Caller must handle the new exception | A09/A04 | Informational (verify) |

The change itself is safe. I recommend merging it with a follow-up ticket to fix the race condition in item 1, since it affects the integrity of payment records.