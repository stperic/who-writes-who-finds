# Review of `interface/forms/eye_mag/report.php`

## High severity

**1. SQL injection in `display_draw_image()`**
```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```
- `$filename` is built from `$pid` and `$encounter`.
- At the top of the file, both can be overwritten directly from `$_REQUEST['ptid']` and `$_REQUEST['encid']`.
- This is injectable. Use a bound parameter: `sqlQuery("... LIKE ?", array('%'.$filename))`.
- The query also does not restrict by patient, so a `LIKE '%…'` suffix match could return another patient's document.

**2. SQL built by string concatenation in `narrative()`**
```php
$sql = "select * from facility where id=" . $_SESSION['pc_facility'];
```
- The value comes from the session, not the request, but this is still raw concatenation.
- Use `sqlQuery("... where id=?", array($_SESSION['pc_facility']))`.

**3. Patient/encounter IDs taken from the request without authorization (IDOR)**
```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```
- These override the session patient context with no `acl_check()`.
- They also skip any check that the encounter belongs to the patient.
- Any authenticated user can render any patient's full eye exam and PHI by changing the URL.
- Add an ACL check, cast the values to int, and verify the pid/encounter relationship.

**4. Stored XSS: database fields echoed without escaping**
Many values come from clinician-entered free text but are printed raw:
- `<?php echo $HPI1; ?>`
- `echo "&nbsp;".$CHRONIC2` and `$CHRONIC3`
- IMPPLAN output: `$item['codetext']`, `$item['code']`, `$item['plan']`. For `plan`, only newlines are replaced, then it is echoed raw.
- `$PLAN` items and `$PLAN2`
- `$note->get_note()` in `display_draw_image()`
- `$providerNAME` in the PDF signature block
- `$CTLOSVA` (every neighboring cell uses `text()`)
- `$MOTILITY_*` cells
- `$filetoshow` and `$pid` inside `<img src='...'>`. Combined with issue #3, `$pid` is request-controlled.

Fix: wrap these in `text()`/`attr()`. For `plan`, escape first and then apply `nl2br`.

**5. Short open tags (`<?`) will break the file where `short_open_tag=Off`**
- After the CC2 block there is a bare `<?`:
  ```php
  </div>
  <?
  }
  if ($CC3) {
  ```
- With short tags disabled, the following code is emitted as HTML and the `if ($CC2) {` block is never closed. The result is a parse error.
- Replace with `<?php`. One more `<?` sits inside the commented DRAW block.

## Medium severity

**6. `$choice` is never set: case mismatch**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
- The condition checks `CHOICE` but reads `choice`.
- So `$choice` is null unless both keys exist, and the DRAW/TEXT modes described in the docblock never activate.

**7. `$choice == "narrative"` renders nothing**
```php
} else if ($choice !="narrative") {
  narrative(...);
}
```
- The docblock says a missing choice means "narrative", i.e. display everything.
- Yet an explicit `choice=narrative` produces an empty report. The final branch should be a plain `else`.

**8. Clinical data displayed incorrectly (copy/paste and typo bugs)**
These matter clinically: findings are mislabeled or silently hidden.
- **Motility, left eye, bottom row:** shows `$MOTILITY_LLIO` twice. The first cell should be `$MOTILITY_LRIO`.
- **Near VA:** the condition `if ($ODNEARVA_1||$WNEAROSVA_1)` uses a misspelled variable (`$WNEAROSVA_1`). An OS-only near VA is not shown.
- **Gonioscopy:** `if ($ODGONIO||$OSDGONIO)` has a typo (`$OSDGONIO`). OS-only gonioscopy is hidden.
- **NPC:** `if ($ODNPC or $OSNPC)` refers to variables that don't exist (the field is `$NPC`). NPC is never displayed.
- **Retina gate:** the condition checks only `OD*` fields plus `$OSDISC`. OS-only macula, vessel, or periphery findings suppress the whole Retina section.
- **Additional data gate:** `$PAMODBA` is a typo for `$PAMODVA`. The gate also checks only OD fields.
- **Refraction gate:** `if ($ODVA||$OSVA||...)` checks `$ODVA`/`$OSVA`, but wearing RX values live in `$ODVA_1` etc. A visit with only "current RX" data will not show the refraction table.
- **Autorefraction comments:** use `${"COMMENTS_$i"}` after the RX loop has finished, so `$i == $count_rx+1`. This variable is undefined or unrelated to autorefraction.
- **RX type label:** `$RX_TYPE` is not reset when `RX_TYPE_$i` has an unexpected value, so the previous RX's type leaks into the next row.

**9. `extract()` and variable-variables clobber local scope**
- Top level: `$$LOCATION = text($prefs['GOVALUE']);` lets DB-driven prefs overwrite any global, e.g. `$pid` or `$encounter`.
- `@extract($encounter_data)` pulls in `form_encounter.*` and `form_eye_mag.*`. These include `pid`, `encounter`, `id`, `date` and more, silently overwriting function parameters. The `@` hides failures.
- Prefer explicit array access, or at least `EXTR_SKIP`.

**10. Join queries can return the wrong form**
- Neither query filters `forms.formdir = 'eye_mag'`.
- `form_eye_mag.id = forms.form_id` can therefore match another form type with the same numeric id in the same encounter.
- `eye_mag_report()`'s query also omits `forms.deleted != '1'`.
- `narrative()` is missing `forms.pid = form_eye_mag.pid`.

**11. Signature date is misleading**
- `xlt('electronically signed on')." ".oeFormatShortDate()` prints *today's* date, not the actual signing or encounter date.
- On a medico-legal document, this misrepresents when the note was signed.

**12. Patient photo and drawings use filesystem paths in PDF mode**
- `<img src='$from_file'>` exposes absolute server paths in the PDF HTML.
- This depends on html2pdf filesystem access. It should be documented or handled consistently.

## Low severity / maintainability

**Undefined or uninitialized variables**
- `$css_header` is used in `narrative()` but not declared `global`, so the stylesheet link is empty.
- `$bad` is uninitialized.
- `$IMPPLAN_items` is uninitialized. `foreach` warns when there are no rows.
- `$display_Add` is undefined.
- `$id` is undefined at top level.

**Missing `echo`**
- `title="<?php xla('Variation in red color...'); ?>"` has no `echo`, so the tooltip is empty.

**Broken translation key**
- `xlt('sc Near{{without correction near')` is missing the closing `}}`.

**Untranslated strings**
- "Full to CF OU"
- "Orders/Next Visit:"
- "Comments:" in the autorefraction block

**Malformed HTML**
- **Pupils:** the `<td>` is opened when `$PUPIL_NORMAL=='1'`, but closed only inside the inner `if ($ODPUPILSIZE1||...)` block.
- **ACT:** `</tr><tr>` sits inside `if ($ACT5CCDIST)`, so row structure depends on data.
- **Column counts:** the RX header has 10 columns while the title row uses `colspan=9`. The CTL header has 9 columns.
- **Invalid attributes:** `style="report_vitals" style="..."` and `heght=75`.

**Debug leftovers**
- `xlt('Type').$count_rx` prints the RX count in the column header.
- The query parameter is named `blahblah=rand()`.
- Unused values: `$titleres`, `$facility`, `$visit_date` (in `narrative`), `$extension`, `$to_file`, `$fname`.

**Dead code**
- `left_overs()` references undefined `$table_name`/`$id`.
- `full_report()` returns on its first line.
- There is a large commented-out DRAW block.
- Unused `$formname` parameter.
- These should be removed rather than merged.

**Missing date guard**
- `new DateTime($encounter_date)` silently uses "now" when no row is found. Guard against an empty result.

**Duplicated code and formatting**
- The document path resolution logic is duplicated (patient photo and `display_draw_image`) and should be extracted.
- The HPI and refraction blocks are repeated three to five times. Loops would avoid the copy/paste errors listed in #8.
- Indentation is inconsistent, there are mixed HTML/PHP styles, and the file lacks a trailing newline.

## Recommendation
Request changes. Issues 1–5 (SQL injection, IDOR, XSS, short tags) must be fixed before merge. The clinical display bugs in #8 should also be fixed, since they cause findings to be mislabeled or silently omitted from patient reports.