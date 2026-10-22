## Review: new `interface/forms/eye_mag/report.php`

This file should not be merged in its current form. It has a SQL injection, stored XSS, and a missing authorization check, plus several correctness bugs in the rendered report.

### High severity

**1. SQL injection in `display_draw_image()`**
- Location: `display_draw_image()`, the query `"SELECT * from documents where documents.url like '%".$filename."'"`.
- `$pid` and `$encounter` are concatenated into the SQL string. `$pid` comes from `$_REQUEST['ptid']` and `$encounter` from `$_REQUEST['encid']`, neither of which is validated or cast. The `LIKE` pattern also allows `%` and `_` wildcards.
- Fix: use a parameterized query (`sqlQuery($sql, array(...))`) and build the pattern from validated integers, or cast `$pid`/`$encounter` to int at the top of the file.

**2. Stored XSS from unescaped output**
Several values are echoed without `text()` or `attr()`:
- `$HPI1`, `$HPI2`, `$HPI3` in `narrative()`. These are free-text HPI fields.
- `$CHRONIC2`, `$CHRONIC3`, `$PLAN2`, and the `$PLAN_items` loop.
- `$item['code']`, `$item['codetext']`, and `$item['plan']` in the IMPPLAN loop.
- `$note->get_note()` in `display_draw_image()`.
- `$CTLOSVA` in the contact lens block.
- `$from_file` in `<img src='...'>` in the PDF branches.

Each of these should be wrapped in `text()`, `attr()`, or `report_ACT()` as appropriate. If any field is intentionally rich text, it needs an explicit sanitizer, not raw output.

**3. Missing authorization and patient/encounter binding**
- `eye_mag_report()` and `narrative()` run no `acl_check()`. Other encounter forms in this codebase are gated by the caller's ACL checks, but this file can also be reached directly with arbitrary `ptid`/`encid`/`formid`.
- The queries check `form_eye_mag.pid = $pid` and `forms.pid = form_eye_mag.pid`, but never check `form_encounter.pid = $pid`. An encounter belonging to another patient can be rendered under the requested patient's ID.
- Fix: add an ACL check for encounter/patient access and add `form_encounter.pid = ?` to the queries.

### Medium severity

**4. Motility values are never populated**
- Location: the `$zone` loop in the MOTILITY box, `($$zone[$i] >= '1') ? ($$zone[$i] = ...)`.
- `$zone` is an array, so `$$zone[$i]` resolves to the variable named by the stringified array, not `$MOTILITY_*`. The `-` prefixing never applies to the intended variables.
- The left-eye grid's bottom row prints `$MOTILITY_LLIO` twice and never prints `$MOTILITY_LRIO`.

**5. Variable-variables and `@extract` driven by database contents**
- Location: the preferences loop (`$$LOCATION = text(...)`) and `@extract($objQuery)`, `@extract($encounter_data)`.
- Variable names come from database column names and preference `LOCATION` values. A crafted `LOCATION` such as `_SESSION` or `GLOBALS` could overwrite superglobals. `@extract` also silently overwrites local state such as `$encounter`, `$pid`, `$id`, and `$cols` with any colliding column name, and the `@` hides the failures.
- Fix: whitelist allowed `LOCATION` keys and read values into an explicit array rather than extracting.

**6. Field conditions reference wrong or nonexistent variables**
- Visual acuity: `if ($ODNEARVA_1||$WNEAROSVA_1)` should be `$OSNEARVA_1`. The OS near-VA row is hidden when only OS is recorded.
- Gonioscopy: `if ($ODGONIO||$OSDGONIO)` should be `$OSGONIO`.
- NPC: `if ($ODNPC or $OSNPC)` tests variables that are never set, but the row prints `$NPC`.

**7. Wrong `$_REQUEST` key**
- Location: `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`
- The condition and the assignment use different case, so `$choice` is effectively never set from the request. Callers that rely on `choice` (for example the encounter mouseover) will get the default branch.

**8. Inconsistent deleted-form filtering**
- `eye_mag_report()`'s query does not filter `forms.deleted != '1'`, but `narrative()`'s does. Deleted forms can therefore appear in one report path and not the other.

**9. Wrong global key for web root**
- Location: patient photo and signature image URLs use `$GLOBALS['webroot']`. Elsewhere the code uses `$web_root`/`$GLOBALS['web_root']`. Depending on configuration this produces broken image URLs.

### Low severity

**10. Undefined variables used before assignment**
- `$bad` is incremented in the VF loop without initialization, then compared with `$bad < '1'`.
- `$IMPPLAN_items` is iterated with `foreach` without initialization; it warns when there are no IMPPLAN rows.
- `$display_Add` is used in a class attribute but never defined.
- `$table_name` is used in `left_overs()` and is undefined.
- `$choice` is referenced in `eye_mag_report()` without being set in some paths.

**11. Fragile include path**
- `require_once("../../forms/".$form_folder."/php/...")` is relative to the working directory or include path, not the file. The rest of the file uses `dirname(__FILE__)`.

**12. Dead code**
- `left_overs()` is never called.
- `full_report()` returns immediately, leaving the rest unreachable.
- Large commented-out blocks, including the `DRAW`/`drawing` legacy code and the `pend` inputs.
- Maintainability suffers, and the dead code references variables that no longer exist.

**13. Generic global function names**
- `narrative`, `display_draw_image`, `full_report`, `left_overs`, and `report_ACT` are global. These names are likely to collide with other form modules.
- `report_ACT()` is misnamed; it is used to format plain comments.

**14. Size and duplication**
- At about 2,000 lines, the file repeats the same label/value table markup dozens of times and the same patient-photo and document-path logic in several places. The table rendering and the photo/document path logic should be helper functions.

**15. Invalid markup**
- `<table style="report_vitals" style="font-size: 8px;...">` has a duplicated `style` attribute and a non-CSS value.
- The `<td>` for the Fields box is opened in one branch and closed in another, which is hard to verify.

**16. Silent date fallback**
- `new DateTime($encounter_date)` with a null or missing value silently becomes "now". The report would show today's date for a missing encounter rather than failing visibly.

### Summary

Blocking: the SQL injection (1), stored XSS (2), and the missing authorization and patient binding (3). Items 4 through 9 are correctness bugs that produce wrong or missing clinical data and should be fixed before merge. The rest are cleanup.