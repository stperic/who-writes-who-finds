# Review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

**Summary:** This change fixes a real SQL injection in `ORDER BY`. Before, `$search->getField()` was put straight into the SQL text. The column whitelist is the right fix. A few issues remain.

---

### 1. Signature change will break callers not in this diff
**Location:** method signature (new required `array $allowedColumns`)
**Severity:** High (correctness / availability)

The new parameter is required and has no default. Any caller still using `buildSortOrderClauseFromConfig($config)` will throw an `ArgumentCountError` (a fatal error) at runtime. Likely callers include the REST/FHIR services and `BaseService`-derived search paths. No caller updates appear in this diff.

**Action:**
- Confirm every call site is updated in this PR, or add the updates.
- Do not add `= []` as a default to avoid the break. That would silently turn off sorting everywhere. A default that means "allow anything" would bring the injection back.

### 2. Pre-existing SQL injection: confirm callers pass a static whitelist
**Location:** callers of this method; the old line `$clauses[] = $search->getField() . " " ...`
**Severity:** Critical (pre-existing; the fix depends on callers)

The old code was directly injectable through client-supplied sort parameters, such as `_sort` on the API. The whitelist only protects you if `$allowedColumns` comes from server-side constants or schema metadata. It must never come from request data or anything derived from it.

**Action:** Check each caller. Something like `array_keys($request->getQueryParams())` passed as the whitelist would defeat the fix.

### 3. No escaping of the identifier (defense in depth)
**Location:** `$clauses[] = $field . " " . ...`
**Severity:** Low

`QueryUtils` is already imported. Quoting the identifier as well, for example with `QueryUtils::escapeColumnName` or backtick-quoting, would guard against a careless whitelist entry or a column name that is a reserved word. A whitelist entry like `table.col` needs both parts quoted separately.

### 4. Disallowed sort fields are silently dropped
**Location:** the `continue` branch in the loop and the final `return ""`
**Severity:** Medium (API correctness)

If a client asks for an unsupported sort, the results come back unsorted (or partly sorted) with no error. The client may wrongly assume the order is correct, which also matters for pagination consistency.

**Action:** Consider one of these:
- throw a validation exception that maps to HTTP 400 / FHIR `OperationOutcome`;
- at minimum, log the rejected fields.

### 5. Strict, case-sensitive matching
**Location:** `in_array($field, $allowedColumns, true)`
**Severity:** Low

Strict comparison is correct for security. However, `Fname` versus `fname`, or `pd.fname` versus `fname`, will be rejected silently (see #4).

**Action:** Document the expected format of whitelist entries. If case-insensitive matching is wanted, normalize the field name before comparing, but always emit the whitelisted value rather than the user's input.

### 6. Changed emptiness check
**Location:** `if ($searchOrders === [])`
**Severity:** Low

`empty()` was changed to `=== []`. If `getSearchFieldOrders()` can ever return `null`, the `foreach` will now emit a warning.

**Action:** Confirm the return type is always an array, or keep a null-safe check.

### 7. Missing tests
**Severity:** Medium

The PR should add unit tests covering:
- an allowed field;
- a disallowed or injection payload, such as `fname; DROP TABLE x` or `(SELECT ...)`;
- a mix of allowed and disallowed fields;
- an empty whitelist;
- ASC/DESC handling.