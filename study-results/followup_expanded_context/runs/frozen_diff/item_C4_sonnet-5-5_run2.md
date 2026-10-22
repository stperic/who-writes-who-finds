# Review of `interface/forms/eye_mag/report.php`

## Critical / High

1. **SQL injection in `display_draw_image()`.**
   - `"SELECT * from documents where documents.url like '%".$filename."'"` builds `$filename` from `$pid` and `$encounter`.
   - Both can be overridden from `$_REQUEST['ptid']` and `$_REQUEST['encid']`, so this is exploitable.
   - Use bound parameters.
   - `_` and `%` in a LIKE are also wildcards, and the lookup is not scoped to the patient. It can return another patient's document.
   - `"select * from facility where id=" . $_SESSION['pc_facility']` is also concatenated and should be parameterized.

2. **Missing authorization and IDOR (top of file).**
   - `ptid`, `encid`, `formid` and `formname` are taken straight from `$_REQUEST` and override `$pid`, `$encounter` and `$form_id`.
   - There is no ACL check (for example `acl_check('patients','med')`) and no check that the encounter belongs to the patient or session patient.
   - Any logged-in user can read any patient's eye exam by changing the parameters.

3. **Stored XSS from unescaped output.** These values are echoed without `text()`:
   - `$HPI1`
   - `$CHRONIC2` and `$CHRONIC3`
   - `$item['codetext']`, `$item['code']` and `$item['plan']` (the `str_replace` for `<br />` does no escaping)
   - `$PLAN` items and `$PLAN2`
   - `$note->get_note()`
   - `$CTLOSVA`
   - the `$MOTILITY_*` values
   - `$providerNAME` in the PDF branch
   - `$form_folder` and `$pid` in URLs and attributes, where `attr()` or `urlencode` is needed

4. **Variable-variable and `extract` injection.**
   - `$$LOCATION = text($prefs['GOVALUE'])` assigns arbitrary global variable names from DB data.
   - `@extract($objQuery)` and `@extract($encounter_data)` do the same with DB column names.
   - This is fragile and unsafe. Column names like `id`, `pid`, `date` or `user` from `form_encounter.*` and `form_eye_mag.*` silently clobber each other.
   - The `@` suppresses errors, and `extract` of a `false` result emits warnings.
   - Use an explicit array instead.

5. **`$$zone[$i]` is wrong on PHP 7+.**
   - It is parsed as `($$zone)[$i]`, so the motility values are never transformed. This needs `${$zone[$i]}`.
   - `text()` is also applied to the prefs at assignment time and again at output, which risks double encoding.

## Medium (correctness)

6. **Request parameter mismatch.** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` tests an uppercase key but reads a lowercase one, so `choice` is almost never set.

7. **Inverted logic in `eye_mag_report`.**
   - `else if ($choice != "narrative") narrative(...)` means an explicit `narrative` choice renders nothing.
   - This contradicts the comment that the default is the narrative.
   - The `'DRAW'` and `'TEXT'` casing is inconsistent with the commented-out `'drawing'` and `'narrative'`.

8. **Variable typos that make conditions never or always true.**
   - `$WNEAROSVA_1` should be `$OSNEARVA_1`.
   - `$OSDGONIO` should be `$OSGONIO`.
   - `$PAMODBA` should be `$PAMODVA`.
   - `$ODNPC or $OSNPC` is never set, so the NPC row never shows.
   - `$ODK2AXIS` and `$OSK2AXIS` are suspect.

9. **Wrong motility cell.** The OS bottom row uses `$MOTILITY_LLIO` twice. The first cell should be `$MOTILITY_LRIO`.

10. **Uninitialized or stale variables.**
    - `$bad` is incremented without being initialized.
    - `$IMPPLAN_items` is undefined when there are no rows, so `foreach` emits a warning.
    - `$display_Add` is undefined.
    - `$RX_TYPE` retains the previous iteration's value, or is undefined, for unknown types.
    - The `COMMENTS_$i` block in the Autorefraction section reuses the loop index `$i`, and its "Comments:" label is untranslated.
    - `$count_rx` is the string `'0'`.
    - `xlt('Type').$count_rx` looks like leftover debug output.

11. **Narrative query is not scoped to the form type.**
    - It joins `forms` on `encounter` and `form_eye_mag.id=forms.form_id` but never checks `forms.formdir='eye_mag'`.
    - It also does not check `forms.pid`.
    - `form_id` values from other form types can collide and return the wrong data.
    - `eye_mag_report` has no `forms.deleted` filter.
    - `display_draw_image` requires `$document_id > '1'`, which skips document id 1.

12. **Broken output and markup.**
    - `<?php xla(...)` in the Red Desaturation `title` has no `echo`.
    - `xlt('sc Near{{without correction near')` is missing its closing `}}`.
    - Short open tags (`<?` and `<? ?>`) depend on `short_open_tag`.
    - `<table style="report_vitals" style=...>` has a duplicate attribute.
    - Several `<tr>`/`<td>` nesting errors, for example the Fields `<td>` opened inside a conditional, and the ACT table closing `</tr><tr>` mid-structure.
    - The invalid CSS `0.in` and `padding:5 5 10 5` has no units.
    - `<?php xla` strings contain a literal `$` in "OD=$1.00".

## Low / maintainability

13. **Dead and unused code.**
    - `left_overs()` uses undefined `$table_name` and `$id`.
    - `full_report()` returns immediately, so everything after is dead.
    - Large commented-out blocks remain.
    - Duplicate `print("<tr>\n")` lines.
    - Unused variables (`$titleres`, `$facility`, `$extension`, `$to_file`, `$fname`).
    - `if ($choice !== 'TEXT') { ?> <?php }` is an empty block.

14. **Deprecated globals.** `$fake_register_globals` and `$sanitize_all_escapes` are used. `$sanitize_all_escapes=true` causes the repeated escaping to be unpredictable.

15. **Fragile file paths and cache-busting.**
    - Filesystem paths are built from `$_SESSION['site_id']`, and `file_exists` is called with `$providerID` in the name.
    - `&blahblah=".rand()` is used as a cache-buster.
    - The PDF branch embeds absolute filesystem paths.
    - Photo lookup uses `documents.foreign_id` without ordering or a limit.

16. **Structure.**
    - A ~2000-line file mixes logic, SQL and HTML, with massive copy-paste of near-identical rows.
    - The refraction rows and ACT grids should be loops or helpers.
    - The file lacks a trailing newline and has trailing whitespace.
    - Hardcoded English strings ("Comments:", "Orders/Next Visit:") are not translated.