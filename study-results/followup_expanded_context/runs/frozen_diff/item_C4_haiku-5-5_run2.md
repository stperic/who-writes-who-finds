## Review: `interface/forms/eye_mag/report.php` (new file, ~2060 lines)

I'd block this merge on the SQL injection and the unescaped output. The rest are correctness bugs and maintainability problems that should be fixed before merge.

### Critical / High

**1. SQL injection in `display_draw_image()`**
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **Problem:** `$filename` is built by concatenating `$pid` and `$encounter`. Both come from `$_REQUEST['ptid']` and `$_REQUEST['encid']` (set at the top of the file), with no validation or casting. The query uses `LIKE` with unparameterized input, so a crafted `encid` can inject SQL. The `LIKE` pattern also accepts `%` and `_` wildcards.
- **Fix:** Use a parameterized query (`sqlQuery($sql, array(...))`) and cast `$pid`/`$encounter` to int, or validate them before use.
- **Severity:** High (SQLi, reachable by any logged-in user who can load the report).

**2. Unescaped output of database values (XSS)**
- **Locations and examples:**
  - `echo $HPI1;`, `echo $HPI2;` etc. are not wrapped in `text()`. `HPI1` is free-text clinical data.
  - `echo $CHRONIC2`, `echo $CHRONIC3`, and `echo "&nbsp;".$CHRONIC2`.
  - `echo $PLAN2`, `echo $item` (from `explode('|', $PLAN)`).
  - `echo $item['codetext']`, `echo $item['code']`, `echo $item['plan']`.
  - `echo $note->get_note()` in `display_draw_image()`.
  - `echo ($CTLOSVA?:"-")` and the `$MOTILITY_*` values after they are prefixed with `-`.
  - `$display_Add` in a `class` attribute and `$background` inside a `style` attribute.
- **Problem:** These fields are user-entered and stored, so a stored XSS payload in any of them will execute in the report. Several are also echoed through `text()` elsewhere, so the inconsistency suggests they were missed rather than intentionally left raw.
- **Fix:** Wrap each in `text()` (or `attr()` for attributes). Keep `plan` and `note` as rich text only if they are explicitly sanitized first.
- **Severity:** High.

**3. No ACL check**
- **Location:** top of file. `acl.inc` is required, but no `acl_check()` is ever called.
- **Problem:** Any authenticated user who can reach this script can load any patient's eye exam report by changing `ptid`/`encid`/`formid`. Check whether `globals.php` or the caller enforces patient-data ACL; if not, add it.
- **Severity:** High (depending on the surrounding access model).

### Medium

**4. Motility variable-variable bug**
- **Location:** Motility block, `($$zone[$i] >= '1') ? ($$zone[$i] = "-".$$zone[$i]) : ...`
- **Problem:** In PHP 7+, `$$zone[$i]` is parsed as `($$zone)[$i]`, which dereferences a variable named after the array (`"Array"`). It should be `${$zone[$i]}`. As written, the motility markers are never set correctly, and an "Array to string conversion" notice is raised on every iteration.
- **Severity:** Medium (incorrect clinical output).

**5. Motility grid typo**
- **Location:** Left-eye motility table, last row.
- **Problem:** The bottom row reads `MOTILITY_LLIO`, `MOTILITY_LI`, `MOTILITY_LLIO`. The last cell should be `MOTILITY_LRIO`. The right-eye grid is correct.
- **Severity:** Medium (wrong data displayed).

**6. Wrong variable in visual-acuity condition**
- **Location:** `<?php } if ($ODNEARVA_1||$WNEAROSVA_1) { ?>`
- **Problem:** `$WNEAROSVA_1` is never set. The row is hidden whenever only the left-eye near acuity is present. Should be `$OSNEARVA_1`.
- **Severity:** Medium.

**7. Gonioscopy condition typo**
- **Location:** `if ($ODGONIO||$OSDGONIO)`
- **Problem:** `$OSDGONIO` is not a field used anywhere else; should be `$OSGONIO`. Left-eye gonioscopy will be hidden when only it has a value.
- **Severity:** Medium.

**8. Request parameter typo**
- **Location:** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`
- **Problem:** The condition checks `CHOICE` but reads `choice`. Since PHP request keys are case-sensitive, this either never sets `$choice` or sets it from a value that wasn't validated. Likely meant to be `isset($_REQUEST['choice'])`. Also, `$choice` is left undefined otherwise, triggering notices.
- **Severity:** Medium.

**9. Unchecked `$_REQUEST` values flowing into globals**
- **Location:** top of file, and `@extract($objQuery)` / `@extract($encounter_data)`.
- **Problem:** `@extract()` silently overwrites any variable in scope with whatever the query returns, including `$pid`, `$encounter`, `$form_id`, and `$form_name`. The `@` suppresses warnings. Also, the preferences loop does `$$LOCATION = ...` from a DB column, which lets stored data create or overwrite arbitrary globals (for example `LOCATION` set to a security-relevant name). Replace with explicit `$row['field']` access, or at least use `extract(..., EXTR_SKIP)`.
- **Severity:** Medium.

**10. Missing-row handling**
- **Location:** `eye_mag_report()` and `narrative()`, `new DateTime($encounter_date)`.
- **Problem:** If the query returns no row (`sqlQuery` returns false or null), `$encounter_date` is undefined. `new DateTime(null)` silently uses the current time, which would print today's date on a report for a missing encounter. There is no guard for an empty result.
- **Severity:** Medium.

**11. Undefined variables**
- **Location:** `$bad` in the Fields section (`$bad++` on an unset variable), `$display_Add`, `$ODNPC` (never extracted, so the NPC row relies on `$ODNPC or $OSNPC` being set elsewhere), and `$IMPPLAN_items` (not reset before use).
- **Problem:** Each triggers PHP notices and can produce wrong results. Initialize them explicitly.
- **Severity:** Medium.

**12. Broken title attribute**
- **Location:** `<span title="<?php xla('Variation in red color ...'); ?>">`
- **Problem:** Missing `echo`, so the title is empty.
- **Severity:** Low.

### Low / Maintainability

**13. Dead and broken code**
- `left_overs()` references `$table_name` and `formFetch`, neither defined in scope.
- `full_report()` returns immediately and never runs. Remove it or move it to documentation.
- A large commented-out block in `eye_mag_report()` should be deleted.

**14. Duplicated logic**
- The photo/image path resolution in `narrative()` and `display_draw_image()` is nearly identical. Extract a helper.
- The `Note` rendering is also duplicated in `narrative()` and `display_draw_image()` paths.

**15. Inconsistent globals**
- `$GLOBALS['webroot']` and `$GLOBALS['web_root']` are both used, and `$web_root` is declared `global` in `display_draw_image()` but never read. `$GLOBALS["webserver_root"]` appears in one place and `webroot` elsewhere. Pick one and verify it exists.

**16. Invalid HTML**
- `<table style="report_vitals" ...>` puts a class name in the `style` attribute.
- `<img ... heght=75>` in the commented block (typo, but dead code).
- `<?php echo "<i>".xlt('Timing'); ?>:</i>` splits the tag across PHP blocks and is hard to read.

**17. Length and structure**
- A single 2000-line file mixes data fetch, business logic, and markup, with ~60 `echo ... ?:"-"` expressions. Splitting into a data-preparation function and a template would make review and testing much easier.

### Summary

The critical items are the SQL injection in `display_draw_image()`, the unescaped stored-XSS-prone output, and the missing ACL check. The motility variable-variable bug and the several copy-paste typos (`WNEAROSVA_1`, `OSDGONIO`, `LLIO`, the `CHOICE`/`choice` mismatch) will produce incorrect clinical output and should be fixed before merge. The remaining items are cleanup.