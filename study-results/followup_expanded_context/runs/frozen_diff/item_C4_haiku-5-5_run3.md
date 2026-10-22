# Review: `interface/forms/eye_mag/report.php` (new file, ~2060 lines)

I would not merge this as written. The most serious problems are a SQL injection, missing authorization checks, and several unescaped outputs. There are also a number of functional bugs.

## Security

**1. SQL injection in `display_draw_image()` — Critical**
`$pid` and `$encounter` come from `$_REQUEST['ptid']` and `$_REQUEST['encid']`. They are concatenated into a raw query:
```php
$filename = $pid."_".$encounter."_".$side."_".$zone."_VIEW.jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
This is called from every drawing section. Use a bound parameter. Escape `%` and `_` in the LIKE pattern, or compare on a computed path instead.

**2. No ACL or patient-access check — High**
The file never calls `acl_check` (or equivalent) for the patient or encounter. Anyone with a session can request `report.php?ptid=X&encid=Y` and read another patient's clinical data. Add a `patients`/`med` ACL check, and confirm the encounter belongs to the pid.

**3. Stored XSS through unescaped output — High**
Several values are echoed without `text()` or `attr()`:
- `$HPI1`, `$CHRONIC2`, `$CHRONIC3`, `$CTLOSVA`
- `$item['codetext']`, `$item['code']`, `$item['codetype']`, `$item['plan']` in the Impression/Plan loop (free-text, user-entered)
- `$PLAN_items`, `$PLAN2`
- `$note->get_note()` in `display_draw_image()`
- `$display_Add` used as a class attribute

Wrap each in `text()`. For the Impression/Plan `plan` field, the `str_replace` for newlines should run after escaping.

**4. Data-driven variable injection — Medium**
At top level:
```php
$LOCATION = $prefs['LOCATION'];
$$LOCATION = text($prefs['GOVALUE']);
```
A row's `LOCATION` value determines which variable is overwritten. This can clobber `$pid`, `$choice`, `$form_id`, or even `$_SESSION`. Whitelist the expected keys or store them in an array.

**5. Unbound SQL fragment — Low**
`"select * from facility where id=" . $_SESSION['pc_facility']` should use a bound parameter, even though the session value is probably trusted.

## Correctness

**6. Request parsing typo — Medium**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
The check tests `CHOICE` but reads `choice`. Also, `$choice` is undefined when the request does not set it, and `$id`/`$form_id` may be undefined on `if (!$id) $id=$form_id;`.

**7. `@extract()` on query results — Medium**
`@extract($objQuery)` and `extract` on `form_encounter.* , form_eye_mag.*` overwrite local variables silently, including `id` and `date`, which exist in both tables. The `@` hides the problem. If `sqlQuery` returns `false` (no matching encounter), `$encounter_date` is undefined and `new DateTime()` silently uses the current date. Check for a missing row and fail explicitly.

**8. Motility variable-variable bug — Medium**
```php
for (...) { ($$zone[$i] >= '1') ? ($$zone[$i] = "-".$$zone[$i]) : ...; }
```
`$zone` is an array, so `$$zone[$i]` does not resolve to `$MOTILITY_*`. The conversion never happens, and the `-` markers never render. Use `${$zone[$i]}`.

**9. Motility OS grid has wrong cells — Medium**
The bottom row of the left-eye table is `MOTILITY_LLIO, MOTILITY_LI, MOTILITY_LLIO`. The first cell should be `MOTILITY_LRIO`, which is never displayed.

**10. Deleted forms not filtered in `eye_mag_report()` — Medium**
`narrative()` filters `forms.deleted != '1'`, but `eye_mag_report()` does not. The two queries can return different forms.

**11. Undefined variables used — Low**
- `$bad` is used with `++` and compared without initialization.
- `$count_rx` is used in the refraction header when no wearing rows exist.
- `$ODNPC`/`$OSNPC` are tested, but only `$NPC` is displayed.
- `$ODPUPILSIZE1`/`$OSPUPILSIZE1` logic: `(!$a || !$b)` is probably meant as `(!$a && !$b)`.

**12. Translation/function bugs — Low**
- `<span title="<?php xla('...'); ?>">` calls `xla()` without `echo`, so the title is empty. This occurs in several places.
- `xlt('sc Near{{without correction near')` is missing its closing `}}`.
- Typos in translation keys: `Cyinder`, `Constaast`.
- `<table style="report_vitals" style="...">` has a duplicate attribute, and `report_vitals` is not a valid style value.

**13. Inconsistent globals — Low**
`$GLOBALS['webroot']` and `$GLOBALS['web_root']` are both used, and `$GLOBALS["webserver_root"]` appears alongside `$GLOBALS["fileroot"]`. Some of these may be undefined in a given install.

**14. `global $visit_date` after assignment — Low**
In `eye_mag_report()`, `$visit_date` is assigned locally before `global $visit_date`, so the global is not what the assignment wrote to.

## Maintainability

**15. Dead and commented code — Low**
`left_overs()`, `full_report()` (which returns immediately), the commented DRAW block, and several commented HTML lines add noise. `left_overs()` also references undefined `$table_name`. Remove them or move them to a separate file.

**16. Single 2000+ line file mixing data loading, HTML, and PDF branching — Low**
Splitting the data loading, the per-section renderers, and the PDF/non-PDF switches would make the file reviewable and testable. The repeated `$PDF_OUTPUT` branches and duplicated photo/image code in `narrative()` and `display_draw_image()` are good candidates for helpers.

**17. Minor — Low**
- The `<img ... heght=75>` typo is in dead code, but it should be removed with that code.
- The file has no trailing newline.

## Summary

| # | Location | Issue | Severity |
|---|---|---|---|
| 1 | `display_draw_image()` | SQL injection via `ptid`/`encid` | Critical |
| 2 | file-wide | No ACL / patient-encounter check | High |
| 3 | narrative, impplan loop, etc. | Unescaped output (stored XSS) | High |
| 4 | top-level prefs loop | Data-driven `$$LOCATION` overwrite | Medium |
| 5 | top-level `$_REQUEST['CHOICE']` | Typo; undefined `$choice`/`$id` | Medium |
| 6 | `@extract`, missing-row handling | Silent overwrites, wrong date | Medium |
| 7 | motility loop | `$$zone[$i]` does not resolve | Medium |
| 8 | motility OS table | Wrong cell, `LRIO` missing | Medium |
| 9 | `eye_mag_report()` | Missing `deleted` filter | Medium |
| 10 | various | Undefined variables, `xla` without echo, typos | Low |
| 11 | file-wide | Dead code and mixed concerns | Low |

Address items 1–3 before anything else, then the medium-severity correctness bugs, with a test that renders a report for a patient that has motility and pupil data.