# Security Review: `src/PaymentProcessing/Recorder.php`, `getNextSequenceNumber()`

**No security vulnerabilities found** in this change or in the code it touches.

## What the change does
- Changes the return type from `string` to `int`.
- Checks that the query returned a row with a numeric `increment`. If not, it throws a `RuntimeException` instead of returning `null` or garbage.

## OWASP Top 10 (2021) checklist

| Category | Result |
|---|---|
| A03 Injection (SQL) | **Safe.** The query uses `?` placeholders with `$patientId` and `$encounterId` passed as bound parameters. The SQL is a static nowdoc (`<<<'SQL'`) with no interpolation. |
| A01 Broken Access Control | Not applicable. This is a private helper. Authorization for the patient or encounter is the caller's job and is unchanged here. |
| A04 Insecure Design | The new validation is an improvement. It fails closed rather than producing a bad sequence number. |
| A09 Logging / Error Handling | The exception message is generic. It exposes no patient IDs, SQL, or other sensitive data. |
| A02, A05, A06, A07, A08, A10 | Not applicable to this code. |

## Non-security observations

**1. Race condition (existing, documented in the code comment).** Two concurrent requests for the same `pid`/`encounter` can both read the same `MAX(sequence_no)` and insert duplicate sequence numbers.
- **Impact:** This is a data integrity problem in financial (AR) records. It is not an attacker-exploitable vulnerability.
- **Fix options:**
  - Compute the value in the `INSERT ... SELECT`.
  - Use `SELECT ... FOR UPDATE` inside a transaction.
  - Add a unique constraint on `(pid, encounter, sequence_no)` and retry on conflict.
- **Priority:** Worth fixing for correctness, not as a security issue.

**2. Return type change.** Callers that compared the old return value as a string, or relied on it being a string, should be checked. Under `declare(strict_types=1)`, passing the `int` to a `string` parameter would raise a `TypeError`. This affects functionality, not security.

**Verdict:** Approve from a security perspective.