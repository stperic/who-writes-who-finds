# Review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

The intent is good. Whitelisting sort columns closes a real SQL injection vector, since ORDER BY identifiers cannot be bound as parameters. There are several issues I'd raise before merge.

---

### 1. Breaking signature change: required parameter added to a public static method
**Location:** `buildSortOrderClauseFromConfig(SearchQueryConfig $config, array $allowedColumns)`
**Severity:** High (blocking unless all callers are updated in this PR)

`$allowedColumns` is required and has no default. Any caller still using the one-argument form will throw an `ArgumentCountError` at runtime. This includes:
- core services such as `BaseService` and the FHIR/REST search services,
- modules,
- third-party code.

The diff only touches this file.

Please do one of the following:
- Include every call-site update in this PR and grep the repo, including `interface/` and `modules/`.
- Or, if this is meant to be a staged migration, provide a transition path. One option is a nullable default that logs a deprecation warning. Failing closed would be preferable, but that should be an explicit decision.

---

### 2. `empty()` → `=== []` changes behavior for non-array returns
**Location:** `if ($searchOrders === []) {`
**Severity:** Medium

`empty()` previously handled `null` (and `false`) gracefully. If `getSearchFieldOrders()` can return `null`, two things now go wrong:
- the guard is bypassed,
- `foreach` emits a "foreach() argument must be of type array|object" warning.

The same applies if it returns a collection object: an empty collection is not `=== []`, though the later `$clauses === []` check would still save you there.

Please verify the declared or actual return type of `getSearchFieldOrders()`. If it isn't strictly `array`, either keep `empty()` or add `?? []` / a type check. The later `$clauses === []` check is fine because `$clauses` is always a local array.

---

### 3. Disallowed sort fields are silently dropped
**Location:** the `continue` inside the loop
**Severity:** Medium (reliability/debuggability)

A client requesting `_sort=foo` on a non-whitelisted field gets unsorted or partially sorted results with no signal. This causes two problems:
- **Hidden caller misconfiguration.** A caller whose whitelist is missing a legitimate column will see sorting quietly stop working, and that is hard to diagnose.
- **Misleading results for API consumers.** For FHIR/REST, the spec expectation is generally to report unsupported sort parameters, for example via an `OperationOutcome` warning or a 400, rather than ignore them.

Suggestions:
- At minimum, log at debug or warning level when a field is rejected.
- Better, throw a specific exception, or return the rejected fields, so the API layer can decide how to respond.

---

### 4. Strict, case-sensitive matching may break previously working sorts
**Location:** `in_array($field, $allowedColumns, true)`
**Severity:** Low–Medium

Strict comparison is correct for security. However, previously any casing or qualified form (`lname`, `LNAME`, `p.lname`) passed through. After this change, these are rejected unless the whitelist contains that exact string.

Please make sure each caller's whitelist matches the exact field strings that `SearchFieldOrder::getField()` produces. Pay particular attention to table-alias-qualified names versus bare names.

---

### 5. Whitelist validates identity but couples API names to SQL identifiers
**Location:** design of `$allowedColumns`
**Severity:** Low (maintainability)

The client-supplied field name is emitted directly into SQL once it matches. This is safe, but it forces API-facing sort names to equal SQL column expressions.

A map such as `['name' => 'p.lname', 'birthdate' => 'p.DOB']` would:
- decouple the public parameter from the schema,
- avoid exposing column names,
- still be injection-safe, because only map values ever reach SQL.

Consider this as a follow-up if not in this PR.

---

### 6. Missing tests
**Severity:** Medium

This is a security-relevant change, and the diff includes no unit tests. I'd expect tests for:
- an allowed field producing the correct ASC/DESC clause,
- a disallowed or injection-style field (e.g. `"id; DROP TABLE patient_data--"`, `"(SELECT ...)"`) being excluded,
- a mix of allowed and disallowed fields keeping only the allowed ones in order,
- all fields disallowed returning `""`,
- an empty whitelist returning `""`,
- empty or `null` search orders returning `""` with no warnings.

---

### 7. Minor
- **Duplicate sort fields are not deduplicated** (e.g. `ORDER BY lname ASC, lname DESC`). This is harmless but could be normalized.
- **The `@copyright 2026` line** should be confirmed as intentional and consistent with project conventions.
- **The docblock** could state that rejected fields are silently ignored, if that behavior is kept, so callers know what to expect.

---

**Summary:** This is the right fix for ORDER BY injection. It should not merge until:
- call sites are updated, or a migration path is provided (#1),
- the `null`-handling regression is verified (#2),
- tests are added (#6).

Please also reconsider silent dropping of rejected fields (#3).