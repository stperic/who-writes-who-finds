# Code review: `interface/forms/eye_mag/report.php`

## Critical / High

### 1. SQL injection and cross-patient document leak in `display_draw_image()`

```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```

- **SQL injection.** `$encounter` is concatenated directly into the SQL.
  - In `custom_report.php` it comes from `$form_encounter = $val`, which is a raw `$_GET`/`$_POST` value.
  - It can also come from `$_REQUEST['encid']` at the top of this file.
- **PHI leak.** The leading `%` wildcard has no `foreign_id = pid` filter. A pattern for pid=1, encounter=5 (`%1_5_OU_EXT_VIEW.jpg`) also matches `11_5_OU_EXT_VIEW.jpg` and `21_5_...`. Another patient's drawing can be shown in this patient's report.
- **Fix:**
  - Bind parameters.
  - Add `AND foreign_id = ?`.
  - Match the exact filename or path suffix.
  - Also note that `$document_id > '1'` wrongly excludes document id 1.

### 2. File-scope request handling overrides the patient context when included

`custom_report.php` does `include_once ".../forms/$formdir/report.php"`. That means all top-level code in this file runs in the report's global scope:

```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```

- A request parameter can silently switch `$pid` for the entire custom report, with no ACL check. This is an IDOR that exposes other patients' data.
- **Fix:** Move this code out of `report.php`. It should only define functions.

### 3. Variable-variable injection from preferences at global scope

```php
$LOCATION = $prefs['LOCATION'];
$$LOCATION = text($prefs['GOVALUE']);
```

- This runs in the global scope of `custom_report.php`.
- A pref row whose `LOCATION` is `pid`, `PDF_OUTPUT`, `printable`, `auth_med`, etc. will clobber core globals.
- At minimum, whitelist the names. Better, put prefs in an array.

### 4. Short open tags (`<?`) in live code

- In the CC2 block: `<?\n }` before `if ($CC3)`.
- On servers with `short_open_tag=Off`, the `}` is emitted as text and the file fails to parse. That breaks every patient report that includes eye_mag.
- **Fix:** Use `<?php`.

### 5. Stored XSS — many DB fields echoed without escaping

Unescaped output:

- **HPI / chronic problems:**
  - `$HPI1` (note that `$HPI2`/`$HPI3` are escaped, so this is inconsistent).
  - `$CHRONIC2` and `$CHRONIC3`.
- **Impression/Plan (IMPPLAN):**
  - `$item['codetext']` and `$item['code']`.
  - `$item['plan']`, which only gets newline→`<br />` conversion and no escaping. Use `nl2br(text(...))`.
- **Orders:** `$PLAN` items and `$PLAN2`.
- **Notes and signature:** `$note->get_note()` and `$providerNAME` in the PDF signature.
- **Exam values:** `$CTLOSVA` and all `$MOTILITY_*` values.
- **Image paths:** `$from_file` and `$filetoshow` in `src` attributes, and `$form_folder` in the Amsler `img src`.

### 6. `extract()` clobbers function parameters and the queries can pick the wrong form

- In `narrative()`, `@extract($encounter_data)` pulls in `form_encounter.*` and `form_eye_mag.*`. This includes `pid`, `encounter`, `id`, and the aliased `form_id`, overwriting the `$form_id` argument passed by the caller.
- **The query ignores the requested form:**
  - It does not filter by the `$form_id` the caller asked for.
  - It does not filter `forms.formdir='eye_mag'`.
  - It does not join `forms.pid`.
- **Consequences:**
  - With multiple eye_mag forms in one encounter, an arbitrary one is shown.
  - Any other form in the encounter whose `form_id` collides with a `form_eye_mag.id` can also match.
  - The wearing and impplan lookups then use the wrong `$form_id`.
- The same `extract` pattern in `eye_mag_report()` overwrites `$id`/`$pid`.
- **Fix:** Query by `form_eye_mag.id = ?` and `formdir = 'eye_mag'`. Read fields from the array instead of extracting.

### 7. `$choice` handling is broken

```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```

- **Case mismatch:** the condition checks `CHOICE` but the assignment reads `choice`, so it essentially never works.
- **Inverted default:** in `eye_mag_report()`, the final branch is `else if ($choice != "narrative")`. A `$choice` of `"narrative"` renders nothing, contrary to the doc comment ("If it is not present it will display everything == 'narrative'").

## Medium — clinical-data correctness

### 8. Left-eye motility grid shows the wrong field

- The bottom-left cell shows `$MOTILITY_LLIO`; it should be `$MOTILITY_LRIO`. As written, `LLIO` is displayed twice and `LRIO` never.

### 9. Motility variable-variable is ambiguous across PHP versions

- `$$zone[$i]` means `${$zone[$i]}` in PHP 5 but `($$zone)[$i]` in PHP 7+. This breaks on newer PHP.
- **Fix:** Use `${$zone[$i]}`.

### 10. Typos in display conditions that hide or misreport findings

- `$ODNEARVA_1||$WNEAROSVA_1` should use `$OSNEARVA_1`.
- `$ODGONIO||$OSDGONIO` should use `$OSGONIO`.
- `if ($ODNPC or $OSNPC)` displays `$NPC`, so the condition never matches the displayed value. Use `if ($NPC)`.
- **Retina:** the condition `$ODDISC||$OSDISC||$ODCUP||$ODMACULA||$ODVESSELS||$ODPERIPH` omits the OS fields. Left-eye-only findings are not printed.
- **Refraction box:** gated on `$ODVA||$OSVA`, which don't exist (the wearing data is `ODVA_1`, …). Current glasses Rx is omitted unless some other refraction exists. Check `$count_rx > 0`.
- **Red Desaturation:** `title="<?php xla(...) ?>"` is missing `echo`.
- **ACT:**
  - The table renders when `$ACT != 'on'`. Verify this logic is intended.
  - The string `'sc Near{{without correction near'` is missing its closing `}}`.

### 11. Autorefraction comments use a stale loop variable

- `${"COMMENTS_$i"}` is used after the Rx loop, where `$i == $count_rx+1`. It is undefined, or at best reads the wrong Rx's comment.

### 12. Leftover debug output

- `xlt('Type').$count_rx` prints the Rx count in the column header.

### 13. Malformed HTML breaks html2pdf layout

- **Pupils:** the `<td>` is closed only inside the `if ($ODPUPILSIZE1||...)` branch. The "normal only" path leaves it unclosed.
- **ACT:** `</tr><tr>` sits inside the `if ($ACT5CCDIST)` block, so rows are unbalanced when ccDIST is absent.
- **Column counts:** the refraction header has 10 cells but uses `colspan="9"`.
- **Style attribute:** `<table style="report_vitals" style="...">` has a duplicate `style` attribute (it should be `class`).

## Low — maintainability and robustness

- **Unsafe facility query:**
  - `"select * from facility where id=" . $_SESSION['pc_facility']` is string concatenation; bind it.
  - The result (`$facility`) and `$titleres` are never used.
- **Undefined variables:**
  - `$css_header` inside `narrative()` is not declared global, so the stylesheet `href` is empty.
  - `$display_Add` is undefined.
  - `$bad` is uninitialized.
  - `$IMPPLAN_items` is uninitialized, so `foreach` warns when there are no rows.
- **Dead code:**
  - `left_overs()` references undefined `$table_name`/`$id`.
  - `full_report()` is unreachable after `return;`.
  - There is a large commented-out `DRAW` block.
  - `display_draw_image()` computes an unused base image, `$to_file`, and `$extension`.
- **Redundant work:**
  - `eye_mag_report()` runs a query only to compute `$visit_date`, which is unused.
  - The `$formname` parameter is ignored.
- **Duplication:** the HPI blocks repeated ×3, the refraction rows, and the ACT grids repeated ×4 should be loops or helpers.
- **Error suppression:** `@extract` hides errors. Remove the `@`.
- **Deleted documents shown:** the patient photo and drawing lookups do not exclude deleted documents.
- **Header block:** the duplicated license header still contains the Sketch plugin MIT text, which is unrelated to this file.
- **Missing newline:** the file has no newline at EOF.