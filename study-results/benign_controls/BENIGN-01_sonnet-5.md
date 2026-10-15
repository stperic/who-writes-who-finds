Reviewing the diff for the sort-clause whitelist change.

**1. Breaking signature change — no default value (High/Blocking)**
`buildSortOrderClauseFromConfig()` now requires a second, non-optional `$allowedColumns` parameter. Every existing call site must be updated in the same PR or this throws a fatal `ArgumentCountError`. Since only this file is in the diff, confirm all callers (and any tests) were updated; otherwise this breaks the build.

**2. Silent dropping of disallowed sort fields (Medium)**
When a field isn't in `$allowedColumns`, it's silently skipped via `continue`. If a caller passes a user-controlled field that gets filtered out, the user gets no sort order and no error — making it hard to debug legitimate misconfigurations, and also means attempted injection of a bogus column is never logged, losing a chance to detect probing/attack attempts.

**3. Behavior change: `empty($searchOrders)` → `$searchOrders === []` (Low/Medium)**
This now only short-circuits on exactly an empty array. If `getSearchFieldOrders()` can ever return `null` or another falsy non-array value, the old code safely returned `""` but the new code will fall into `foreach` on a non-iterable, causing a warning/error. Worth confirming `getSearchFieldOrders()`'s return type is strictly `array` (a type hint on that method would make this moot).

**4. Column format assumptions (Low)**
The whitelist comparison is a strict `in_array` against raw `getField()` output. If `getField()` ever returns qualified names (e.g. `t.name`) or expressions, the whitelist must be kept in the exact same format at every call site, which is easy to get out of sync and silently lose sort fields (ties into #2). Not a bug here, but a maintenance trap — consider documenting the expected format or centralizing the allowed-columns lists near the call sites.

**5. No test coverage shown (Low)**
The diff doesn't include tests for: a disallowed field being filtered out, all fields being filtered out (empty clause path), and the previous "no sort config" path. Given this is a security-relevant whitelist, explicit tests would help prevent regressions.

Overall the core change (adding a column whitelist to prevent SQL injection via sort field) is a good, legitimate fix — the concerns above are about safe rollout (#1), observability (#2), and robustness (#3), not the underlying approach.
