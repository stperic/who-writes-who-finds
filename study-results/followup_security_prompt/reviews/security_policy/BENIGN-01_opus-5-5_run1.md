# Security Review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

## Summary

**I found no security vulnerabilities in this diff.** The change fixes a SQL injection flaw (OWASP A03:2021 – Injection) that existed before it.

## The Pre-Existing Issue This Change Fixes

| Field | Detail |
|---|---|
| **Location** | `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`, old line `$clauses[] = $search->getField() . " " . ...` |
| **OWASP Category** | A03:2021 – Injection (SQL Injection) |
| **Problem** | The value from `$search->getField()` was concatenated directly into an `ORDER BY` clause. Column names and sort expressions cannot be parameterized with prepared-statement placeholders. If the sort field came from a request (e.g. a FHIR/REST `_sort` parameter), an attacker could inject SQL, such as `(CASE WHEN (SELECT ...) THEN id ELSE pid END)` or `SLEEP(5)`. This allows boolean-based or time-based blind extraction of data, including PHI. |
| **Severity (before fix)** | **High** |
| **Status** | **Remediated** by this diff |

## Why the Fix Is Sound

1. **Allowlist rather than blocklist.** Only exact matches against `$allowedColumns` are put into the query. This is the correct defense for identifiers that cannot be bound as parameters.
2. **Strict comparison.** `in_array($field, $allowedColumns, true)` prevents PHP type-juggling bypasses. For example, a non-string value cannot loosely match an entry.
3. **Sort direction is not attacker-controlled text.** It comes from the boolean `isAscending()` and maps only to the literals `ASC` or `DESC`.
4. **Fails closed.** Invalid fields are dropped. If no valid fields remain, an empty string is returned instead of a malformed `ORDER BY`.
5. **The allowlist is mandatory.** `$allowedColumns` is a required parameter, so no caller can silently skip validation. Any existing caller that does not pass it will fail loudly, not insecurely.

## Recommendations (Not Vulnerabilities)

These are hardening notes and items to verify. They are not findings against this diff.

- **Check the callers (not visible in this diff).** The protection is only as good as the `$allowedColumns` each caller passes.
  - The list must be built from hard-coded, trusted column names, never from request input.
  - It must not be derived wholesale from something like `array_keys($_GET)`.
  - Every caller of this method should be reviewed in the same PR, since the signature change forces them to be updated anyway.
- **Allowlist entries are inserted verbatim.** Entries containing aliases or qualified names (e.g. `p.lname`) are fine as long as they are developer-defined constants.
- **Optional logging (A09:2021 – Security Logging and Monitoring Failures, informational).** Rejected sort fields are silently discarded. Logging rejected values at debug or warn level would help detect probing attempts, but this is optional and low priority.
- **Behavioral note.** Clients that request an unsupported sort field will now silently get default ordering. Consider whether the API should return a 400 error or an `OperationOutcome` warning instead. This is a correctness concern, not a security one.

## Conclusion

**Approve from a security perspective.** No new vulnerabilities are introduced, and the change correctly fixes a previously high-severity SQL injection vector. The only open item is confirming that every caller supplies a trusted, hard-coded allowlist.