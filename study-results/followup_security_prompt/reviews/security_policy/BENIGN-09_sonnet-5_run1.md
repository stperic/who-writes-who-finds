## Review of `interface/main/calendar/find_group_popup.php`

### Finding 1 — Removal of `isset($result)` guard
**Location:** Lines around the removed `<?php if (isset($result)) : ?> ... <?php else : ?> ... <?php endif; ?>` block.

**OWASP category:** A05:2021 – Security Misconfiguration (information disclosure via error messages) / general code-quality regression that can cascade into availability issues.

**Problem:** The diff deletes the check that only renders the results table when `$result` is set, and removes the "No groups found" fallback. `$result` is only assigned inside the earlier `if ($searchby && $searchparm) { ... }` block. If that condition is false (e.g., user loads the popup without search parameters, or a malformed/empty request), `$result` will be **undefined** by the time the table-rendering code below (not shown in the diff, but referenced via the `foreach`/`?>`/`</table>` loop) executes.

Consequences:
- On PHP 7/8 this triggers an "Undefined variable $result" notice/warning, and the subsequent loop (`foreach ($result as ...)`) will emit a `foreach() argument must be of type array|object, null given` warning.
- If `display_errors` is enabled (a common misconfiguration in dev/staging environments, and sometimes accidentally in production), these warnings can leak file paths and internal application structure to the browser — an information-disclosure issue.
- Functionally, the "No groups found" UX is now silently lost, which is a correctness regression but not itself a high-severity security bug.

**Severity:** Low (information disclosure contingent on misconfigured error display; otherwise just a functional bug).

**Recommendation:** Restore a guard, e.g. `if (!empty($result)) { ... } else { ... "No results" ... }`, or initialize `$result = []` before the conditional logic so the table loop is always safe.

---

### Observations on code this change touches but doesn't show (needs review, not confirmed vulnerable from this diff alone)

Because the diff only shows the rendering portion, I cannot verify from this patch alone whether the following pre-existing concerns apply — they should be checked in the full file before merging:

- **Potential SQL Injection (A03:2021):** The surrounding logic uses `$searchby` / `$searchparm` to build a query (implied by `if ($searchby && $searchparm) { ... }` constructing `$result`). Confirm these values are passed through parameterized queries (e.g., `sqlStatement()` with bound parameters) rather than concatenated into SQL strings.
- **Reflected XSS (A03:2021):** Confirm every value from `$result` printed in the table body uses `text()`/`xlt()`/`attr()` escaping functions, consistent with the `text(count($result))` call shown here. If any field (e.g., group name/description) is echoed without `text()`/`attr()`, that's a reflected XSS risk.
- **Broken Access Control (A01:2021):** This popup should enforce that the current authenticated user/session has permission to search calendar groups (e.g., ACL check such as `acl_check('admin','superbill')` or similar, depending on module). Confirm this check exists earlier in the file and wasn't affected by this diff.

These are flagged for completeness per the review scope ("flaws in code this change touches or relies on"), not confirmed vulnerabilities, since the relevant lines are outside the provided diff.

---

### Summary
- The diff itself introduces one **Low severity** issue: removal of the `isset($result)` check, which can cause PHP warnings/notices on an undefined variable and loss of the "no results" message, with a minor information-disclosure risk if error display is misconfigured.
- No SQL injection, XSS, CSRF, or broken access control issues are directly introduced by the visible diff, but the surrounding (unshown) code that builds `$result` from `$searchby`/`$searchparm` and renders it should be reviewed to confirm parameterized queries and output escaping are in place, and that an ACL/session check gates access to this popup.