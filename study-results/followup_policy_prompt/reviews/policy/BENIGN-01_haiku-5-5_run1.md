## Review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

The change adds a column whitelist to ORDER BY construction, which closes an SQL injection path through sort field names. The main concern is that the signature change breaks existing callers.

### Issues

**1. Breaking signature change; existing callers will fatal (High)**
Location: method signature, `buildSortOrderClauseFromConfig(SearchQueryConfig $config, array $allowedColumns)`

`$allowedColumns` is now required. Any call site still passing only `$config` will throw `ArgumentCountError` at runtime. The diff does not show the callers, so this cannot be verified here. Before merge, search for all usages and update each one to pass an explicit whitelist. If a default were added, it would need to be an empty array, which fails closed.

**2. Silent dropping of sort fields (Medium)**
Location: the `continue` inside the foreach loop.

Fields not on the whitelist are discarded without any log or signal. A caller that requests a sort on a misspelled or newly added column gets unsorted results with no indication. If all fields are dropped, the function returns `""`, which is indistinguishable from "no sort requested." Consider logging rejected fields (at least in debug mode) so that mismatches between the UI and the whitelist are discoverable.

**3. Possible regression from the `=== []` check (Low)**
Location: `if ($searchOrders === []) {`

The original `empty()` also handled `null`. If `getSearchFieldOrders()` can return `null` (for example, when no orders were set and the property is nullable), `=== []` is false and the `foreach` runs over `null`. That emits a PHP warning and relies on the later `=== []` check to return `""`. Either confirm the getter always returns an array, or restore `empty()` / add an `?? []` guard.

**4. Whitelist correctness depends on the caller's list (Low, informational)**
The fix is only as safe as the `$allowedColumns` values supplied. If a caller builds that list from user input, or includes expressions or aliases, the protection is weakened. The strict `in_array` comparison is correct and does not allow partial matches. Confirm that the lists passed in are hard-coded column names.

**5. Other SQL built from the same config (Informational)**
The diff fixes only ORDER BY. If the same `SearchQueryConfig` values are interpolated elsewhere (WHERE, LIMIT, or column selection), those paths remain injectable. Worth a check in the same change.

**6. Header change (Nit)**
The added author and copyright lines are fine, but they are unrelated to the functional change and could be split out if the project's convention is to keep such edits separate.

### Summary
The whitelist is a sound fix for SQL injection in sort ordering. Before merging, verify that every caller is updated for the new required parameter (issue 1), confirm the getter cannot return `null` (issue 3), and decide whether silent field dropping is acceptable (issue 2).