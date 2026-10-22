## Summary

This is a very large new file (2000+ lines) that mixes heavy inline HTML, SQL, and business logic. While most SQL uses parameterized queries (good), there are several real security and reliability problems, plus significant maintainability concerns.

---

### 1. Missing authorization / IDOR check on patient data
**Location:** Top of file, after `$_REQUEST['ptid']` / `$_REQUEST['encid']` are read into `$pid` / `$encounter`.
**Problem:** There is no visible check that the logged-in user is authorized to view this specific patient/encounter (e.g. no `acl_check()`/`AccessDenied` pattern, no verification that `$pid` matches the session's allowed patient). Since `ptid` and `encid` are taken straight from `$_REQUEST`, any authenticated user could potentially view another patient's eye exam report (PHI) by guessing/incrementing IDs.
**Severity:** High (security / PHI exposure)

---

### 2. SQL built via string concatenation (SQL injection risk)
**Location:**
- `display_draw_image()`: `$sql = "SELECT * from documents where documents.url like '%".$filename."'";` where `$filename` is built from `$pid`/`$encounter` which originate from request input.
- `narrative()`: `$sql = "select * from facility where id=" . $_SESSION['pc_facility'];`

**Problem:** Every other query in the file correctly uses `sqlQuery($query, array(...))` with bound parameters, but these two build the query by direct string concatenation. This is inconsistent and reintroduces classic SQL injection risk (especially the `documents.url like '%...'` case, which depends on request-derived values).
**Severity:** High

---

### 3. Inconsistent/missing output escaping → stored XSS
**Location:** `narrative()` function, multiple places, e.g.:
```php
&nbsp;<?php echo $HPI1; ?>                 // not escaped (HPI2/HPI3 ARE escaped with text())
if ($CHRONIC2) echo "&nbsp;".$CHRONIC2."<br />";   // not escaped
if ($CHRONIC3) echo "&nbsp;".$CHRONIC3."<br />";   // not escaped
echo $item['code']."<br />";               // not escaped
echo $item['codetext']."<br />";           // not escaped
echo  $item['plan']."</div><br />";        // not escaped
echo  $item."<br />";                      // $PLAN_items, not escaped
echo $PLAN2."<br />";                      // not escaped
```
**Problem:** Most fields are correctly wrapped in `text()`, but these are echoed raw. Since these come from free-text clinical fields (HPI, Plan, chronic problems, impression/plan text) stored in the database, this is a stored XSS vector whenever a user previously entered HTML/script content in those fields.
**Severity:** High

---

### 4. Logic bug: case-mismatched request parameter
**Location:**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
**Problem:** `$_REQUEST` keys are case-sensitive. The guard checks `'CHOICE'` (uppercase) but assigns from `'choice'` (lowercase). Per the comments, the actual parameter sent by callers is `choice`, so this condition will essentially never be true, and `$choice` will remain unset — defeating the DRAW/TEXT/narrative switch this code is built around.
**Severity:** Medium (functional bug)

---

### 5. Unreliable use of `extract()`, `@` suppression, and variable-variables
**Location:** 
```php
@extract($objQuery);
@extract($encounter_data);
$LOCATION = $prefs['LOCATION']; $$LOCATION = text($prefs['GOVALUE']);
${"ODSPH_$count_rx"} = $wearing['ODSPH']; ... (repeated ~18x per iteration)
```
**Problem:** Using `extract()` on DB result rows to populate dozens of implicit variables, combined with `@` error suppression and dynamic variable names (`$$LOCATION`, `${"X_$i"}`), makes the code very fragile: a DB column rename/collision can silently overwrite `$pid`, `$id`, `$form_id`, etc., and errors are hidden rather than surfaced. This is hard to maintain, impossible to statically analyze, and a known anti-pattern reminiscent of `register_globals`.
**Severity:** Medium (maintainability / latent correctness risk)

---

### 6. Unhandled exception potential
**Location:**
```php
$dated = new DateTime($encounter_date);
$dated = $dated->format('Y/m/d');
```
(in both `eye_mag_report()` and `narrative()`)
**Problem:** If the query returns no row (e.g., mismatched pid/encounter, deleted form), `$encounter_date` is undefined/empty, and `new DateTime('')` can throw an `Exception`, causing a fatal error with no try/catch anywhere in the file.
**Severity:** Medium (reliability)

---

### 7. Undefined variables used directly
**Location:** e.g. `attr($css_header)` in `narrative()` — `$css_header` is never set or globalized in this function; also `$id` is referenced (`if (!$id) $id=$form_id;`) before being defined anywhere in this file; `$display_Add` used in a CSS class with no prior assignment.
**Problem:** Produces PHP notices/warnings and likely renders broken `<link>` tags; indicates incomplete refactor from whatever file this was copied/adapted from.
**Severity:** Low

---

### 8. Large amount of dead/commented-out code
**Location:** The entire block inside `if ($choice == 'DRAW')` wrapped in `/* ... */` (old loop-based doc lookup logic), and the unused `full_report()` / `left_overs()` functions that immediately `return;`.
**Problem:** Dead code left in a production file adds confusion and maintenance burden; should be removed or moved to documentation/history.
**Severity:** Low (maintainability)

---

### 9. Overall file structure / duplication
**Location:** Whole `narrative()` function (~1800 lines).
**Problem:** Massive duplication (CC1/CC2/CC3 blocks, RX type loops done with dynamic variables instead of arrays, repeated `font-weight:400;font-size:1.0em` inline styles scattered hundreds of times). This should be refactored into loops over arrays/templates and shared CSS classes. As written, any bug fix (e.g., the missing-escaping issue above) must be manually found and fixed in dozens of near-identical spots — which is likely how issue #3 happened.
**Severity:** Medium (maintainability, long-term risk)

---

## Recommendation
Before merging:
1. Add an explicit authorization check confirming the current user may access the given `pid`/`encounter`.
2. Convert the two raw-concatenated SQL statements to use bound parameters.
3. Audit all `echo`/output statements in `narrative()` and wrap all DB-sourced strings consistently with `text()` (or `xlt()`/`xla()` for translatable literals).
4. Fix the `$_REQUEST['CHOICE']` / `$_REQUEST['choice']` mismatch.
5. Consider follow-up refactor to eliminate `extract()`/variable-variables and reduce duplication, even if not blocking this merge.