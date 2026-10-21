## Review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

The change adds a column whitelist in front of a string-concatenated `ORDER BY`. That is the right direction, since `ORDER BY` identifiers cannot be bound as parameters and the field names previously went straight into SQL. The issues below are mostly about how the change is rolled out.

### Issues

**1. Breaking signature change: new required parameter (High)**
- **Location:** `buildSortOrderClauseFromConfig(SearchQueryConfig $config, array $allowedColumns)`
- **Problem:** `$allowedColumns` is required with no default. Every existing caller that passes only `$config` will now fail with an `ArgumentCountError` at runtime. The diff doesn't touch any callers, so either they were updated in another part of the PR (not shown) or this will break at runtime. Static analysis won't catch it if the call sites are dynamic.
- **Suggestion:** Confirm all call sites are updated in this PR, and grep for other usages. Add a test or static-analysis check that covers the call sites.

**2. Silent dropping of disallowed fields (Medium)**
- **Location:** the `continue` inside the foreach loop.
- **Problem:** Unknown fields are skipped without any log or error. A typo in a column name, or a caller that forgets to pass the right whitelist, quietly removes the user's sort with no signal. If every field is dropped, the query runs unsorted and returns `""`, which is hard to diagnose.
- **Suggestion:** Log a warning (or debug-level message) when a field is rejected, so misconfiguration is visible.

**3. Whitelist is only as safe as its contents (Medium)**
- **Location:** `in_array($field, $allowedColumns, true)`.
- **Problem:** The security guarantee depends entirely on callers passing a hardcoded, trusted list. If a caller builds `$allowedColumns` from request input or from the same config, the injection protection disappears. The docblock doesn't say the list must be trusted. An empty `$allowedColumns` also silently produces no ORDER BY.
- **Suggestion:** Document that `$allowedColumns` must be a hardcoded developer-defined list. Consider mapping allowed names to their SQL expressions (`['pid' => 'patient_data.pid']`) rather than checking strings, so the output SQL comes only from a fixed map.

**4. Change in null handling (Low)**
- **Location:** `if ($searchOrders === [])` replacing `empty($searchOrders)`.
- **Problem:** `empty()` treats `null` as empty; `=== []` does not. If `getSearchFieldOrders()` can return `null`, `foreach` will emit a warning and the function will proceed. The return type is unchanged in intent, so this is a regression risk even though the change looks cosmetic.
- **Suggestion:** Confirm the getter's return type is `array` (non-nullable). If it is, this is fine; otherwise restore `empty()`.

**5. No tests (Medium)**
- **Problem:** The diff adds behavior (whitelisting, empty-result handling, the new signature) with no test changes shown. Cases to cover: allowed field, disallowed field, mixed list, empty whitelist, empty order list, and ASC/DESC.

**6. Header changes (Low)**
- **Problem:** The diff adds a second author and a 2026 copyright line for OpenCoreEMR. This is a project-policy question, not a code defect. Confirm it matches the repository's convention for who gets listed.

### Summary

The security intent is good, but the PR has a breaking signature change that must be checked against all callers (issue 1), silently drops invalid input without logging (issue 2), and needs tests (issue 5). Issue 3 should be documented so future callers don't pass untrusted input. Overall: **request changes** until callers are verified and tests are added.