## Review result: no security vulnerabilities found in this diff

This change is a security improvement. It fixes an SQL injection risk in `buildSortOrderClauseFromConfig()`.

### What changed
- **Before:** `$search->getField()` was concatenated directly into the `ORDER BY` clause. If the field name came from user input, such as an API `_sort` parameter, this was injectable. Prepared statements cannot parameterize identifiers, so a whitelist is the right fix.
- **After:** each field must pass `in_array($field, $allowedColumns, true)`, otherwise it is skipped. The `ASC`/`DESC` keyword comes from a boolean, so it is not attacker-controlled. If no fields survive, the method returns an empty string rather than a malformed `ORDER BY`.

### Notes (informational, not vulnerabilities)

1. **Safety depends on callers.** The whitelist is only as safe as the `$allowedColumns` each caller passes.
   - Callers must use hardcoded column names, ideally qualified ones such as `table.col`.
   - They must never build the list from request data.
   - Please check every call site. The signature change makes `$allowedColumns` a required parameter, so any missed caller fails loudly with an `ArgumentCountError` instead of silently staying vulnerable. That is a good fail-closed property.

2. **Silent dropping of invalid fields (Security Logging and Monitoring, very low).** Rejected sort fields are ignored without any log entry. Logging them at debug or warning level would help detect probing for injection. It is optional.

3. **Stricter empty check (robustness only).** `empty($searchOrders)` became `$searchOrders === []`. If `getSearchFieldOrders()` could ever return `null`, `foreach` would raise a warning. This is not a security issue. If the method is typed as returning `array`, it is fine.

4. **Other injection points.** Sibling methods in this class, such as the `WHERE`, `LIMIT` and `OFFSET` builders, are outside this diff. If they interpolate config values, they deserve the same review.

**Recommendation:** approve, after confirming that all callers pass static whitelists.