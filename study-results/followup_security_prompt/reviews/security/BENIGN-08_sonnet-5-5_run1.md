## Security review: `Recorder::getNextSequenceNumber`

**Result: no security vulnerabilities found in this diff.**

### What the change does
- It changes the return type from `string` to `int`.
- It validates the query result: it must be an array with a numeric `increment`, otherwise a `RuntimeException` is thrown.
- It casts the value to `int` before returning it.

### OWASP Top 10 (2021) checklist

| Category | Assessment |
|---|---|
| A01 Broken Access Control | Not affected. This is a private method, and the diff changes no authorization logic. |
| A02 Cryptographic Failures | Not applicable. |
| A03 Injection | Not affected. The query uses a heredoc with `?` placeholders and bound parameters (`[$patientId, $encounterId]`), so there is no string concatenation. The `int\|string` types on the inputs are loose, but binding makes that safe. The `(int)` cast on the output removes any type-juggling ambiguity downstream. |
| A04 Insecure Design | See the informational note below. The change does not introduce or worsen it. |
| A05 Security Misconfiguration | Not affected. The exception message is static and contains no SQL, PID, or encounter data, so it leaks nothing if surfaced. |
| A06 Vulnerable Components | No dependency changes. |
| A07 Authentication Failures | Not applicable. |
| A08 Software/Data Integrity Failures | See the informational note below. |
| A09 Logging/Monitoring Failures | Failing loudly with an exception is better than silently returning `null` or an invalid value. Make sure callers don't swallow it silently. |
| A10 SSRF | Not applicable. |

### Informational notes (not vulnerabilities in this PR)
1. **Pre-existing race condition (A04/A08-adjacent).** The comment above the method already notes that `SELECT MAX(...)+1` followed by a separate insert is not atomic. Two concurrent payment postings for the same `pid` and `encounter` could receive the same `sequence_no`. This could cause duplicate or misordered `ar_activity` rows, which is a data-integrity concern in a financial ledger. It is not directly exploitable for privilege gain and is not introduced by this diff. A good follow-up would be to compute the value in a subquery within the `INSERT`, use `SELECT ... FOR UPDATE`, or add a unique constraint on `(pid, encounter, sequence_no)` with retry. Severity: Low/Informational.
2. **Caller handling of the new exception.** Confirm that callers either let the exception roll back the surrounding transaction or handle it deliberately, so a failure doesn't leave a partially recorded payment. This is a correctness concern, not a security one.

**Recommendation:** Approve from a security standpoint.