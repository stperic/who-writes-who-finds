# Security Review: `Recorder::getNextSequenceNumber()`

**No security vulnerabilities are introduced by this diff.** The change is a net improvement in robustness.

## Checklist Results

| OWASP 2021 Category | Finding |
|---|---|
| A03 Injection (SQLi) | **None.** The query uses `?` placeholders bound via `QueryUtils::querySingleRow`. `$patientId` and `$encounterId` are never interpolated. The nowdoc (`<<<'SQL'`) also prevents PHP variable interpolation. |
| A03 Injection (XSS) | **N/A.** No output is rendered. |
| A01 Broken Access Control | **N/A.** This is a private helper. Authorization is the caller's responsibility, and the diff doesn't change it. |
| A04 Insecure Design | Pre-existing race condition only (see below). Not introduced or worsened. |
| A05 Security Misconfiguration / Information Disclosure | **None.** The new exception message is generic and leaks no patient data, SQL, or schema details beyond a table name. |
| A08 Software & Data Integrity | Improved. Previously a `false`/`null` result would cause a PHP warning and an implicit null/empty return. That could insert a bad `sequence_no`. The change now fails closed with an exception. |
| A02, A06, A07, A09, A10 | Not applicable to this change. |

## What the Change Does Well

- **Fails closed:** A failed or empty query now throws instead of returning garbage.
- **Strict typing:** The `is_numeric()` check plus the `(int)` cast guarantees an integer return. This matches the `sequence_no` column semantics.
- **Safe array access:** The `?? null` guard avoids undefined-index notices.

## Informational: Pre-existing Issue (Not Introduced by This PR)

**Location:** `getNextSequenceNumber()`, the `MAX(sequence_no) + 1` pattern
**Category:** A04 Insecure Design (data integrity / TOCTOU race)
**Severity:** Low (informational, pre-existing)

The in-code comment already acknowledges this. Two concurrent payment postings for the same `pid`/`encounter` can read the same `MAX` and both insert the same `sequence_no`. In a payment ledger (`ar_activity`), this can cause:

- duplicate-key failures, if a unique constraint exists, or
- ambiguous or overwritten ledger entries, if no unique constraint exists.

Suggested follow-up, outside this PR's scope:

- Use `SELECT ... FOR UPDATE` inside the same transaction as the insert.
- Alternatively, compute the value in the `INSERT ... SELECT` statement.
- Make sure a `UNIQUE (pid, encounter, sequence_no)` constraint exists, so a collision fails loudly instead of silently corrupting data.

## Non-security Note

The return type changed from `string` to `int`. Verify that callers don't rely on string semantics, such as strict `===` comparisons against string values. Also check that `declare(strict_types=1)` doesn't cause type errors where the value is passed onward.

**Verdict: Approve from a security standpoint.**