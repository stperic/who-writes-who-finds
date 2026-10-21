## Review Comments

**Location:** `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig()` signature change

**Issue:** The method signature changes from `buildSortOrderClauseFunction(SearchQueryConfig $config)` to require a new mandatory parameter `array $allowedColumns`. This is a breaking API change. Every existing call site must be updated in the same commit or the code will fail to compile/run (PHP will throw an `ArgumentCountError`). The diff only touches this one file, so it's important to confirm (and this review can't verify) that all callers across the codebase were updated to pass a proper whitelist. If any caller was missed, this is a hard runtime failure.
**Severity:** High (if callers aren't updated) / informational otherwise — needs verification.

---

**Location:** `foreach ($searchOrders as $search) { ... if (!in_array($field, $allowedColumns, true)) { continue; } ... }`

**Issue:** When a requested sort field isn't in the whitelist, it is silently dropped with no logging, exception, or indication to the caller. This is good from a security standpoint (prevents SQL injection via field name), but from a reliability/UX standpoint, a user/API caller requesting a sort on a field that is mistakenly omitted from the whitelist (e.g., a legitimate column not yet added to `$allowedColumns`) will get back unsorted or partially sorted results with no error — this could be confusing to debug. Consider logging a warning (not necessarily throwing, since this field often comes from external input) so legitimate-but-rejected fields can be diagnosed.
**Severity:** Low–Medium

---

**Location:** `in_array($field, $allowedColumns, true)`

**Issue:** This is an exact/strict string match. If `getField()` can return qualified names (e.g., `table.column`) while `$allowedColumns` contains bare column names (or vice versa), legitimate fields will be silently filtered out. There's no normalization/case-insensitivity handling. This is a potential correctness gap depending on how field names are produced elsewhere in the codebase — not verifiable from this diff alone, but worth a test case.
**Severity:** Low

---

**Location:** General — security context (pre-existing code being touched)

**Issue:** This change is addressing what was previously a SQL injection vulnerability: `$search->getField()` was concatenated directly into a SQL `ORDER BY` clause without any validation. The fix here is good (whitelist approach), but it's worth flagging explicitly in the PR description/changelog as a security fix, and reviewers should confirm:
1. All callers constructing `$allowedColumns` actually use a fixed, hardcoded whitelist (not something derived from user input), otherwise the fix is cosmetic.
2. There isn't another code path elsewhere in `SearchQueryConfig`/`SearchFieldOrder` that bypasses this builder and performs the same unsafe concatenation.
**Severity:** High (important to confirm the fix is complete and not bypassable elsewhere).

---

**Location:** Return type annotation `: string`

**Issue:** Minor — adding a return type is a good practice, but combined with the signature change, this is also technically a breaking change for any subclass that overrides this static method with an incompatible signature (unlikely given it's static, but worth a mental note for strict typing / LSP considerations).
**Severity:** Informational

---

### Summary
The core change (introducing a column whitelist for ORDER BY) is a solid, necessary security fix for a prior SQL injection risk. The main concerns are: (1) verifying all call sites were updated for the new required parameter, (2) silent-drop behavior on invalid fields could mask real problems, and (3) ensuring the whitelist itself isn't inadvertently built from untrusted input at any call site.