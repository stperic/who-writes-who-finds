# Code Review: `interface/main/calendar/find_group_popup.php`

## Summary
The PR removes the `isset($result)` guard around the results table and deletes the `else` branch that showed "No groups found". This causes regressions, and I would not merge it as-is.

## Issues

### 1. Undefined variable / iteration over unset `$result`
**Severity: Medium**
**Location:** Results table block (old lines ~215–249), the row loop that iterates `$result`.

`$result` is only assigned inside `if ($searchby && $searchparm) { ... }`. When the popup first opens, or is submitted without both parameters, `$result` is never defined. The other `count($result)` usage at line 212 is still conditionally wrapped.

With the guard removed, the table code runs unconditionally:
- PHP raises `Warning: Undefined variable $result`.
- If the loop is `foreach ($result as ...)`, PHP 8 also raises `foreach() argument must be of type array|object, null given`.
- If it is `while ($row = sqlFetchArray($result))` or similar, passing `null` to the DB fetch helper may error or behave unpredictably.

**Information-disclosure side effect:** If `display_errors` is enabled, these warnings expose server file paths in the popup HTML.

### 2. Loss of user feedback ("No groups found")
**Severity: Low (UX / functional regression)**
**Location:** Removed `else` branch (old lines 250–252).

The "No groups found" message, which is localized via `xlt`, is gone. Users now see an empty table header with no explanation. If the intent was to show a message for zero matches (as opposed to "no search yet"), the original logic was also imperfect, but deleting it makes things worse.

The translation string may now be unused. That is minor, but worth cleaning up if intentional.

### 3. Unclear intent / missing justification
**Severity: Low (maintainability)**

The PR does not explain why the guard was removed. If the goal was to always show the table header, the safe approach is one of the following:
- Initialize `$result = [];` before the search block.
- Keep the guard and change the `else` branch to handle the empty case, e.g. `if (!empty($result)) ... else <p>No groups found</p>`.

## Suggested fix
```php
// near top, before the search block
$result = [];
...
<?php if (!empty($result)) : ?>
  <div id="searchResultsHeader"> ... table ... </div>
<?php else : ?>
  <p><?php echo xlt("No groups found"); ?></p>
<?php endif; ?>
```

## Security notes on surrounding code (not visible in the diff, please verify)
- **SQL injection:** The search block uses `$searchby` and `$searchparm` from the request. Confirm the query uses bound parameters (`sqlStatement($sql, [$binds])`) rather than string concatenation. Also confirm `$searchby` is mapped to a column name through a whitelist and is never interpolated directly.
- **Output escaping:** In the row loop, every echoed value should be escaped:
  - group name and ID via `text()` / `attr()`;
  - values passed into JS `onclick` handlers (e.g. `selgid(...)`) via `attr_js()` / `js_escape()`.
- **CSRF:** Check whether the search form includes and verifies a CSRF token (`CsrfUtils::verifyCsrfToken`). It is a read-only search, so the impact is low, but OpenEMR convention is to include it.

I can't confirm these from the diff alone. Please verify them before merge, since the change directly affects how this code path renders.