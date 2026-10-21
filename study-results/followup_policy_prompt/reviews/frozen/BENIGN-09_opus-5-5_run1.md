# Review: `interface/main/calendar/find_group_popup.php`

**Summary:** This diff removes the `isset($result)` guard around the results table and drops the "No groups found" fallback. The table-rendering code still assumes `$result` exists, so this is a regression and should not be merged as-is.

---

### 1. Results block now runs when `$result` is undefined
**Location:** around old line 215 (removed `<?php if (isset($result)) : ?>`) and the table body loop (~lines 220–245)
**Severity:** High

`$result` is only assigned inside `if ($searchby && $searchparm) { ... }`. On first load of the popup, or when either parameter is empty, `$result` is never defined.

The block between `searchResultsHeader` and `</table>` almost certainly iterates over it (for example, `foreach ($result as $iter)`). Without the guard, you get:
- an `Undefined variable $result` warning, and
- `foreach() argument must be of type array|object, null given`.

If `display_errors` is on, these warnings are emitted into the popup HTML. That breaks the markup, and file paths in the messages are a minor information-disclosure risk. Even when warnings are suppressed, logs fill with noise on every popup open.

The file's own code shows the guard matters. The "records found" line just above is still wrapped in a conditional (`<?php endif; ?>` at line 213). Only the table lost its guard.

**Fix:** Restore the guard. If the goal was to always show the header, initialize `$result = [];` before the search block and keep a guarded loop.

---

### 2. "No groups found" feedback removed
**Location:** removed `<?php else : ?> <p>…No groups found…</p>` (old lines 250–252)
**Severity:** Medium (UX regression)

Before this change, users saw a localized message when no search had produced a result set. Now they see an empty header table with no explanation. The translation string `xlt("No groups found")` also becomes dead.

If the intent was to show "no results" based on an empty result set rather than an unset variable, use something like `empty($result)` instead of deleting the branch.

---

### 3. Empty header table rendered before any search
**Location:** `#searchResultsHeader` / results `<div>`
**Severity:** Low

Even if warnings are suppressed, the column headers and container now render on initial page load, before the user has searched. This is likely unintended visual clutter. Any JavaScript in the following `<script>` block that assumes these elements exist only after a search may also behave differently.

---

### 4. No stated rationale or tests
**Severity:** Low (maintainability)

The PR does not explain why the guard was removed. If this was meant to fix a specific bug, such as results not showing in some case, the real cause is probably elsewhere (for example, `$result` being assigned under a different condition). That should be fixed directly rather than by removing the guard.

---

### Recommendation
**Request changes.** Either revert this hunk, or initialize `$result` explicitly and replace `isset($result)` with appropriate `empty()`/`count()` handling, keeping a user-visible "No groups found" message.