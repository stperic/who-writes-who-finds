## Security review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

**Verdict:** This diff introduces no new vulnerabilities. It fixes one.

### What the change does
Before, `buildSortOrderClauseFromConfig()` concatenated `$search->getField()` straight into an `ORDER BY` clause. If that field came from a request parameter such as a `_sort` parameter in the API, that was **SQL injection (A03:2021)**. Column names can't be bound as prepared-statement parameters, so the injection was exploitable through subqueries, `CASE`/`IF` expressions, or time-based and boolean blind techniques. The new code checks each field against a caller-supplied allowlist using strict `in_array(..., true)`. Fields not on the list are dropped, and the direction is hardcoded to `ASC` or `DESC`. This is the correct mitigation.

### Residual observations
None of these block the merge.

| # | Location | OWASP category | Observation | Severity |
|---|----------|----------------|-------------|----------|
| 1 | `buildSortOrderClauseFromConfig`, `$allowedColumns` parameter | A04 Insecure Design | The method is only as safe as the list it receives. Every caller must pass a **hardcoded** list, for example from the service's known column map. If any caller builds the list from request data or from `$config`, the protection is bypassed. Reviewers should check each call site. Because the parameter is now required, any caller the PR missed will fail with an `ArgumentCountError`. That is fail-closed, but it is an availability risk if untested. | Low / informational |
| 2 | Same function, `continue` on a rejected field | A09 Logging & Monitoring Failures | Disallowed sort fields are silently ignored. An injection attempt such as `fname; SELECT SLEEP(5)` leaves no trace. Logging a rejection at debug or warning level, without echoing the raw value unsafely, would help detect probing. Silently dropping the field is otherwise reasonable behavior. | Low |
| 3 | Same function, `$field . " " . ...` | A03 Injection (defense in depth) | The allowlisted value is concatenated without quoting or escaping. This is safe only if the allowlist entries are trusted identifiers. Entries should never contain user-influenced text. Qualified names such as `table.col` must be listed exactly as they will be used. | Informational |

### Pre-existing or related items I could not verify
- Only part of the file is shown. If other builders in the class, such as filter, limit, or offset clause builders, concatenate values from `SearchQueryConfig` in the same way, they have the same injection risk and need the same treatment. The `QueryUtils` import suggests other methods exist.
- The same applies to every other place in the codebase that uses `SearchFieldOrder::getField()` or similar values to build SQL. These should be audited.

### Recommendation
Approve. Before merging, confirm that:
1. All call sites pass static allowlists.
2. Tests cover rejection of a malicious field, mixed valid and invalid fields, and the all-invalid case, which should return `""`.
3. Optionally, rejected fields are logged.