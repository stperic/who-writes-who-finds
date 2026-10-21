## Review: `SearchConfigClauseBuilder.php` ORDER BY whitelist

**Verdict: No new security vulnerabilities in this diff. It is a security improvement.**

### What the change does

Before this change, `buildSortOrderClauseFromConfig()` concatenated each sort field name from `SearchQueryConfig` directly into the `ORDER BY` clause. Column names cannot be bound as parameters in SQL, so any user-influenced field name reaching this function was a SQL injection sink (OWASP A03:2021, Injection). The diff adds an allowlist check so only caller-supplied column names pass through.

### Checks on the new code

- **Injection (A03):** Each field is compared with `in_array($field, $allowedColumns, true)`. The strict comparison avoids type-juggling surprises. Unlisted fields are skipped, not interpolated. The direction is a boolean mapped to a fixed `ASC`/`DESC` string, so it cannot inject. The sink is now reachable only with allowlisted names.
- **Fail-closed behaviour:** If no valid fields remain, the function returns `""`, so no `ORDER BY` is emitted. Unknown input is dropped rather than passed through.
- **Type handling:** `$searchOrders === []` is stricter than `empty()`. If `getSearchFieldOrders()` can return `null`, `foreach` will emit a PHP warning. That is a robustness issue, not a security one, and the subsequent `$clauses === []` check still returns safely.

### Things to verify outside this diff (low severity, not defects in the change)

1. **Callers must be updated.** The new required `array $allowedColumns` parameter is a breaking signature change. Any call site still using the one-argument form will throw `ArgumentCountError` at runtime. That fails closed, but it will break search. Grep for all callers.
2. **Allowlist provenance.** The protection holds only if each caller passes a hardcoded, developer-defined list. If a caller builds `$allowedColumns` from request data, the check is bypassed. Confirm the lists are static.
3. **Sink-level exposure elsewhere.** The field name from `SearchQueryConfig` may be used in other places (WHERE, GROUP BY, or other sort helpers) that still concatenate it without validation. Those sites are outside this diff but rely on the same config object, so they should be audited (pre-existing A03 risk).
4. **Silent dropping.** Rejected fields are skipped without logging. This is a minor monitoring gap (A09). Logging rejected sort fields at debug level would help detect probing.
5. **Tests.** No test covers the rejection path or the all-invalid case. Add a unit test that injects a malicious field name (e.g., `id; DROP TABLE x--`) and asserts it produces no output.

### Non-security note

The copyright and author header additions are benign metadata changes.