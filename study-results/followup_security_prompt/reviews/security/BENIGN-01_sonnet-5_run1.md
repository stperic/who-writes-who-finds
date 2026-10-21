## Security Review

**Context:** This diff *adds* a whitelist mechanism (`$allowedColumns`) to `buildSortOrderClauseFromConfig()`, which previously concatenated an unvalidated field name directly into a raw SQL `ORDER BY` clause. That prior behavior was a classic SQL Injection sink (OWASP A03:2021) if `getField()` could ever be influenced by user input (e.g., a `sort` query parameter mapped into `SearchQueryConfig`). This change is a **positive security fix**, not a new vulnerability — but a few residual concerns remain given what's visible in the diff.

### 1. Dependent on correct caller-side whitelist (unverified in this diff)
- **Location:** `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig()` — call sites not shown.
- **OWASP Category:** A03:2021 – Injection (residual risk) / A04:2021 – Insecure Design.
- **Problem:** The fix only works if every caller passes a hard-coded, trusted whitelist of column names (not derived from user input, config files that users can edit, or reflection over user-supplied field lists). Since the call sites are not part of this diff, it cannot be confirmed that the whitelist itself isn't attacker-influenced. If any caller builds `$allowedColumns` dynamically from request data, the protection is bypassed.
- **Severity:** Medium (cannot be fully assessed without seeing callers — flag for follow-up review).

### 2. Silent failure on invalid/rejected sort fields — no logging
- **Location:** `foreach ($searchOrders as $search) { ... if (!in_array(...)) { continue; } ... }`
- **OWASP Category:** A09:2021 – Security Logging and Monitoring Failures.
- **Problem:** When a field fails the whitelist check, it is silently dropped with no logging/alerting. If an attacker is probing for SQL injection via a sort parameter, this failure mode leaves no audit trail, making detection of attack attempts impossible.
- **Severity:** Low.

### 3. Strict type-safety is good, but no input validation error surfaced to caller
- **Location:** Same function.
- **OWASP Category:** A04:2021 – Insecure Design (minor).
- **Problem:** Returning an empty/partial `ORDER BY` clause when all/some sort fields are invalid could mask misconfiguration or malicious tampering as if sorting were simply "not specified," rather than treating it as an error condition the application should respond to explicitly (e.g., 400 Bad Request). Not a direct vulnerability, but a design weakness that reduces observability.
- **Severity:** Low / Informational.

### Summary
No new vulnerabilities introduced by this diff — it correctly remediates what was previously an unparameterized, attacker-influenceable `ORDER BY` clause (SQL Injection risk). Recommend:
1. Auditing all call sites to confirm `$allowedColumns` is always a static, developer-defined list.
2. Adding a log entry (e.g., `warning` level) when a requested sort field is rejected by the whitelist, to support detection of injection attempts.