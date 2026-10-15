## Review: `interface/main/calendar/find_group_popup.php`

**Issue 1 — Regression: "No groups found" message is removed and the results table is now rendered unconditionally**
- **Location:** removed `<?php if (isset($result)) : ?> ... <?php else : ?> <p>...No groups found...</p> <?php endif; ?>` wrapper around `#searchResultsHeader`/`<table>`.
- **Problem:** The table markup (and whatever row-rendering loop lives in the elided section) now always renders, even when `$result` was never set (e.g., page loaded without a search, or `$searchby`/`$searchparm` empty). Users will see an empty table with just headers instead of the "No groups found" feedback. This looks like an unintentional behavioral regression rather than a deliberate UI change — nothing in the diff explains why the fallback messaging was dropped.
- **Severity:** Medium (functional/UX regression).

**Issue 2 — Possible undefined-variable warning / reliability risk**
- **Location:** same removed `isset($result)` guard.
- **Problem:** If the hidden code between the two diff hunks iterates over `$result` (e.g., `foreach ($result as $row)`), and `$result` is only assigned inside the `if ($searchby && $searchparm)` branch earlier in the file, then on initial page load (no search performed) `$result` is undefined. Removing the `isset()` check removes the only safeguard against iterating an undefined variable, which on PHP 8 raises a warning (and a `foreach() argument must be of type array|object` warning) rather than failing silently. Worth confirming `$result` is always initialized (e.g., `$result = $result ?? [];`) before this block, otherwise this is a reliability issue, not just cosmetic.
- **Severity:** Medium (depends on whether `$result` is guaranteed defined elsewhere — please verify).

No security issues (escaping via `text()`/`xlt()` is untouched) and no other correctness problems found in the diff itself.
