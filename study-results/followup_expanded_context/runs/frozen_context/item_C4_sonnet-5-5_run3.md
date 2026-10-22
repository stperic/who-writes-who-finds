## Review of `interface/forms/eye_mag/report.php`

### High severity

1. **SQL injection in `display_draw_image()`.**
   - `$filename` is built from `$pid` and `$encounter` and concatenated into `... where documents.url like '%".$filename."'`.
   - Those values can come from `$_REQUEST['ptid']` and `$_REQUEST['encid']` (lines 41-42).
   - Use a bound parameter and escape the `_` and `%` wildcards.
   - The `$_SESSION['pc_facility']` concatenation in `narrative()` should be bound as well.

2. **Request parameters override `$pid`, `$encounter` and `$form_id`, with no ACL check.**
   - Top of file: `$pid = $_REQUEST['ptid']`, `$encounter = $_REQUEST['encid']`, `$form_id = $_REQUEST['formid']`, `$form_name = $_REQUEST['formname']`.
   - Any logged-in user can view another patient's eye exam, and the report also shows that patient's photo and PMSFH.
   - The file is included by `custom_report.php`, so these assignments run in global scope there too. They can silently change which patient's data is rendered.
   - Remove the overrides, or validate them against the session and ACLs.
   - There is no `acl_check` anywhere in the file even though `acl.inc` is required.

3. **Stored XSS from unescaped output.** These are all free-text clinical fields:
   - `echo $HPI1` (the other HPI fields use `text()`).
   - `$CHRONIC2` and `$CHRONIC3`.
   - `$item['codetext']`, `$item['code']`, `$item['codetype']` and `$item['plan']`. The `str_replace` for line breaks runs before escaping, so `plan` should be `text()`-escaped first and then converted to `<br />`.
   - Each `$PLAN` item and `$PLAN2`.
   - `$note->get_note()` and `$providerNAME` (PDF branch).
   - `$CTLOSVA`, which is not wrapped in `text()` while its OD counterpart is.
   - The `$MOTILITY_*` values are echoed raw.

4. **`$$zone[$i]` behaves differently in PHP 7.** It is parsed as `($$zone)[$i]`, not `${$zone[$i]}`. The motility "-n" formatting breaks, and the loop clobbers variables.

5. **Wrong request key: `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`.**
   - The test key and the read key differ in case. `$choice` is therefore never set from the request, and the mouseover feature (DRAW/TEXT) cannot work.
   - The `$choice != "narrative"` test is also inverted relative to the comment. Passing "narrative" renders nothing.

### Medium severity

6. **Uninitialized variables and warnings.**
   - `$IMPPLAN_items` is undefined when there are no rows, so `foreach` warns.
   - `$bad` is never initialized.
   - `$display_Add` and `$css_header` are used inside `narrative()` without `global`, so the first stylesheet link is empty.
   - `new DateTime($encounter_date)` throws if the query returns nothing.

7. **`@extract($encounter_data)` and `@extract($objQuery)` can overwrite local variables.**
   - The rows come from `form_encounter.*` and `form_eye_mag.*`, so `pid`, `encounter`, `id` and `form_id` can be replaced.
   - The `@` hides the failures.
   - `$$LOCATION = text($prefs['GOVALUE'])` at the top of the file creates arbitrary global variables from DB data, and it also HTML-escapes them up front, which leads to double escaping.

8. **Query problems.**
   - `narrative()` ignores the `$form_id` parameter. It selects by encounter only, so multiple eye_mag forms in one encounter return an arbitrary row.
   - `forms.pid` is not constrained.
   - `eye_mag_report()` has no `forms.deleted` filter.

### Correctness bugs (typos and copy-paste)

- The OS motility grid uses `$MOTILITY_LLIO` twice. The bottom-left cell should be `LRIO`, which is never shown.
- `$ODNEARVA_1||$WNEAROSVA_1` should be `$OSNEARVA_1`.
- `$ODGONIO||$OSDGONIO` should be `$OSGONIO`.
- `$PAMODBA` should be `$PAMODVA`.
- `$ODNPC or $OSNPC` is checked, but only `$NPC` is displayed.
- The Retina condition checks only `OD` fields, plus `OSDISC`.
- The refraction block prints `xlt('Type').$count_rx`, which looks like leftover debug output.
- In the Autorefraction block, `${"COMMENTS_$i"}` uses the stale `$i` from the previous loop. It repeats the last RX's comments, and the English "Comments:" is not translated.
- `$RX_TYPE` keeps its previous value when `RX_TYPE` is not 0-3.
- `<?php xla('Variation in red color...') ?>` has no `echo`, so the title is empty.
- `xlt('sc Near{{without correction near')` is missing its closing `}}`.

### Maintainability and robustness

- `display_draw_image()` uses `$document_id > '1'`, which skips document id 1. It should be `> 0`.
- It also computes `$extension` and `$to_file` and never uses them.
- Mixed use of `$GLOBALS['web_root']` and `$GLOBALS['webroot']`, and an unused `global $web_root`.
- A bare `<?` short tag (after the CC2 block) fails when `short_open_tag` is off.
- The HTML is malformed in places:
  - The pupils `</td>` is only emitted inside the nested `if`.
  - The ACT table has `</tr><tr>` inside a conditional.
  - A `<table style="report_vitals" style=...>` has a duplicate style attribute.
- Hard-coded English strings: "Orders/Next Visit", "Comments:".
- Dead code: `left_overs()` references undefined variables, `full_report()` returns immediately, and there is a large commented-out block.
- Requires use cwd-relative paths (`../../globals.php`, `../../forms/...`). These only work by coincidence when included from `custom_report.php`.
- `rand()` is used as a cache-buster ("blahblah"), and `ob`/`echo` is mixed with large inline HTML. This should be refactored into smaller templates.
- The PDF branch shows the provider name twice.
- The file ends without a trailing newline.