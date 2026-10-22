Review of `interface/forms/eye_mag/report.php`

## High severity

**1. Request parameters override trusted globals at include time (lines 43–50)**
- `custom_report.php` includes every form's `report.php` with `include_once` before it processes anything else. The top-level code here therefore runs inside the patient report.
- `ptid`, `encid`, `formid` and `formname` from `$_REQUEST` overwrite `$pid`, `$encounter`, `$form_id` and `$form_name`.
- Anyone who can open the custom report can append `ptid=<other patient>` and redirect `$pid` to another patient. That bypasses the patient-context check, and the other forms' reports will then use it too.
- `if (!$id) $id=$form_id;` reads an undefined variable.
- Fix: keep this code out of the include path. Move it into a function or a guarded block, and use only the arguments passed to the `*_report()` function.

**2. SQL injection in `display_draw_image()`**
- `$sql = "SELECT * from documents where documents.url like '%".$filename."'";` interpolates `$pid` and `$encounter`.
- Those values can come straight from `$_REQUEST['ptid']` and `['encid']`, so this is exploitable.
- The `LIKE` pattern also matches on a suffix only, so it can return a different patient's drawing. For example, pid 1 + encounter 23 and pid 12 + encounter 3 both give `…_23_…`/`…_123_…`-style suffix collisions.
- Fix: use bound parameters and anchor the match, for example by also filtering on `foreign_id = ?`.
- `"select * from facility where id=" . $_SESSION['pc_facility']` should also be parameterized.

**3. Variable-variable injection from preferences (lines 51–55)**
- `$$LOCATION = text($prefs['GOVALUE'])` takes the variable name from a DB column and sets it in global scope.
- A pref row whose `LOCATION` is `pid`, `encounter`, `GLOBALS` and so on can clobber core state.
- It also creates preference variables as globals in every report that includes this file.
- Fix: whitelist the keys, or store the prefs in an array.

**4. Unescaped output (XSS)**
- `echo $HPI1;`
- `echo "&nbsp;".$CHRONIC2` and `$CHRONIC3`
- `$item['codetext']`, `$item['code']`, `$item['codetype']` and `$item['plan']` in the IMPPLAN section
- `$PLAN` items and `$PLAN2`
- `$providerNAME` in the PDF signature block
- `$CTLOSVA`, the `$MOTILITY_*` values, and `$note->get_note()`
- `$HPI1` and the plan may be intended to hold HTML, but nothing sanitizes them, so stored XSS is possible. Escape with `text()` and `nl2br`, or sanitize explicitly.
- `$_SESSION`/DB-derived file paths are also placed raw into `<img src='…'>`.

**5. Wrong `$choice` handling; the "narrative" branch is inverted**
- `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` tests the upper-case key but reads the lower-case one. `$choice` will almost never be set.
- `else if ($choice != "narrative")` runs `narrative()` for everything except "narrative". The docblock says the default and "narrative" should display everything, so `choice=narrative` currently prints nothing.
- Undefined-index notices are emitted on each request.

## Medium severity

**6. Query joins can pull the wrong or deleted forms**
- Both queries join `forms` without `forms.formdir='eye_mag'`. A `form_id` from another form type can match.
- `eye_mag_report` omits `forms.deleted != 1`. `narrative` omits `forms.pid=?`.
- Both rely on `sqlQuery` returning a single row, which is not guaranteed.

**7. `@extract()` on DB rows**
- `@extract($objQuery)` and `@extract($encounter_data)` hide errors and can overwrite local variables.
- `form_encounter.*` and `form_eye_mag.*` both contain `id`, `pid`, `date` and similar columns, so which value wins depends on the extract order.
- If the query returns false, `new DateTime(null)` silently uses "now".
- Fix: use explicit array access.

**8. Wrong data shown in the motility box**
- In the OS grid, bottom-left uses `$MOTILITY_LLIO` instead of `$MOTILITY_LRIO`. `LLIO` is therefore printed twice and `LRIO` is never shown.
- `$$zone[$i]` parses differently in PHP 7+ (`${$zone}[$i]`) than in PHP 5 (`${$zone[$i]}`). This is fragile and may break outright.

**9. Typos in conditions that hide or misreport data**
- `$ODNEARVA_1||$WNEAROSVA_1` should be `$OSNEARVA_1`.
- `$ODGONIO||$OSDGONIO` should be `$OSGONIO`.
- `$ODNPC or $OSNPC` tests variables that are probably never set (only `$NPC` is displayed).
- `$PAMODBA` should be `$PAMODVA`.
- The "Additional" block's outer condition omits many of the fields it prints.
- The refraction block's outer condition mixes `$ODVA`/`$OSVA` and refraction fields.
- A clinical report that silently drops rows is a patient-safety concern.

**10. Stale loop variable**
- In the Autorefraction block, `if (${"COMMENTS_$i"})` reuses `$i` left over from the Rx loop. It prints the last Rx's comments under autorefraction, with a hard-coded, untranslated "Comments:".
- The Autorefraction section is also missing the `xlt` wrapper for "Comments".

**11. Undefined variables**
- `$bad` is incremented without initialization.
- `$IMPPLAN_items` is undefined when there are no rows, so `foreach` raises a warning.
- `$display_Add`, `$css_header` and `$ODK2AXIS`/`$OSK2AXIS` are never defined here.
- `$count_rx = '0'` is used as a number, and `$bad < '1'` is a string comparison.

**12. Wrong document ID check**
- `if (($document_id > '1') && is_numeric(...))` excludes document id 1. It should be `> 0`, and `is_numeric` should be checked first.

## Low severity

**13. Malformed HTML**
- `<?` short tag at the CC2 block will break when `short_open_tag` is off.
- The ACT `ccDIST` block closes `</tr><tr>` in the middle of the nested `<td>` structure, so the output is invalid.
- The Pupils `<td>` is opened conditionally but closed in a different conditional.
- `<table style="report_vitals" style="...">` has a duplicate `style` attribute.
- `<?php xla('…') ?>` in the Red Desaturation title is missing `echo`.
- Heavy inline styles and layout tables make this hard to maintain and are not very PDF-safe.

**14. Misc quality problems**
- The `HPI` label is printed twice in different formats, and CC3 loses its bold label.
- The mixed `$GLOBALS['web_root']` and `['webroot']` spellings look like a bug.
- `rand()` is used for cache busting.
- `$web_root` is declared global but never defined here.
- File paths are built from DB data without validation.
- Relative `require_once("../../forms/...")` depends on the CWD. Use `dirname(__FILE__)` consistently.
- `left_overs()` references undefined variables and is dead code. `full_report()` returns immediately, leaving unreachable code, with a duplicated `print("<tr>\n")`.
- Generic function names (`narrative`, `display_draw_image`, `report_ACT`) risk collisions in a global namespace shared by all form reports.
- Large commented-out blocks and a typo ("Constaast") remain.
- The file declares AGPL while the rest of the project (for example `custom_report.php`) uses GPL. Check license compatibility.
- The new file has no trailing newline.

**15. Not testable or reviewable**
- The 2000-line file mixes data access, logic and markup with no tests. Splitting out partials would make review feasible.