## Security Review

**Scope:** Small diff hardening `getNextSequenceNumber()` to validate/cast the DB result to `int` and throw if it isn't numeric.

### Finding 1 — Unresolved race condition in sequence number generation
- **Location:** `src/PaymentProcessing/Recorder.php`, `getNextSequenceNumber()`
- **OWASP Category:** A04:2021 – Insecure Design
- **Problem:** The function computes `MAX(sequence_no)+1` via a plain `SELECT`, with no locking read (`SELECT ... FOR UPDATE`) or atomic subquery/insert. The comment directly above the method even acknowledges this: "this still has a potential race condition." Under concurrent requests for the same `patientId`/`encounterId`, two transactions can read the same `MAX(sequence_no)` and attempt to insert duplicate sequence numbers, causing data integrity problems in financial/payment records (`ar_activity`). This diff improves type-safety of the *result* but does not address the underlying concurrency flaw that was called out as a known issue.
- **Severity:** Medium (the impact is data corruption/duplicate financial records, not direct exploitation, but it's in a payment-processing code path, which raises the real-world impact).

### Other OWASP categories checked — no issues found
- **Injection/SQLi:** Query uses parameterized placeholders (`?`) via `QueryUtils::querySingleRow`, values are bound, not concatenated — safe.
- **Broken Access Control / Auth:** No access-control or auth logic touched in this diff.
- **Cryptographic Failures:** N/A, no crypto involved.
- **Security Misconfiguration / Outdated Components:** No config or dependency changes.
- **XSS:** No output/rendering code here.
- **Software/Data Integrity:** The added numeric validation and exception on invalid data is a good practice and improves robustness against unexpected DB return values (e.g., `NULL` or non-numeric), reducing the chance of silent type coercion bugs downstream.
- **Logging/Monitoring:** The new `RuntimeException` doesn't leak sensitive data, which is good; however, it's worth verifying (outside this diff) that the caller logs this failure appropriately for monitoring purposes, since silent failures in payment sequence generation could mask underlying problems.
- **SSRF:** Not applicable to this code.

### Summary
This change itself is a net positive from a defensive-coding standpoint (stricter type/validation handling), and introduces no new vulnerabilities. The one actionable issue is the **pre-existing, explicitly acknowledged race condition** in sequence number generation, which remains unfixed and should be tracked/resolved given its use in payment processing (e.g., via `SELECT ... FOR UPDATE`, a unique constraint with retry logic, or a DB sequence/auto-increment mechanism).