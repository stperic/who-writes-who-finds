# Code review: `interface/forms/eye_mag/report.php` (new file)

**Context.** `custom_report.php` and `encounters_ajax.php` pull this file in with `include_once`. As a result:

- its top-level code runs inside their scope;
- its global function names share their namespace.

Several of the issues below depend on this.

---

## Critical / High

### 1. Top-level code overwrites the caller's `$pid`, `$encounter`, `$form_id` and `$form_name` from `$_REQUEST` (Security, High)
- **Location:** lines ~67–72.
- **Problem:** `custom_report.php` includes every form's `report.php` before it processes the report sections. Any request carrying `ptid` therefore silently switches the patient for the whole report: demographics, history, notes, immunizations, and so on.
  - This bypasses the session-bound patient context and acts as an IDOR across patients.
  - The other three variables, populated from `encid`, `formid` and `formname`, have the same effect on encounter, form ID and form name.
- **Fix:** do not touch globals at file scope in a `report.php`. Move this logic into whatever standalone entry point needs it, and validate it there with ACL checks against the session patient.

### 2. Variable-variables from DB prefs at global scope (Security/Reliability, High)
- **Location:** lines ~76–80, `$$LOCATION = text($prefs['GOVALUE']);`.
- **Problem:** this runs in the includer's global scope. Any pref row whose `LOCATION` is `pid`, `encounter`, `PDF_OUTPUT`, `printable`, `srcdir`, etc. clobbers the host script's variables.
  - The query is also pointless for a report.
- **Fix:** remove it, or store prefs in a local array.

### 3. SQL injection and cross-patient image leakage in `display_draw_image()` (Security, High)
- **Location:** `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **Problem 1 (injection):** `$filename` is built from `$pid` and `$encounter`. `$pid` can come straight from `$_REQUEST['ptid']` (issue #1), so this is injectable. Use a bound parameter.
- **Problem 2 (wrong patient's image):** even with a bound parameter, the query is not scoped to the patient.
  - The leading `%` means pid `1` / encounter `23` also matches `11_23_…` and `21_23_…`.
  - `_` is itself a LIKE wildcard.
  - So another patient's drawing can be rendered into this patient's chart.
- **Fix:** filter on `foreign_id = ?` and match the URL exactly, or escape the wildcards.

### 4. Short open tags `<?` (Reliability, High)
- **Location:** `<?` at the end of the CC2 block and inside the commented DRAW block.
- **Problem:** with `short_open_tag=Off` this causes a parse error. Because `custom_report.php` includes every form's `report.php`, it breaks patient reports for every patient that has an eye_mag form.
- **Fix:** use `<?php`.

### 5. Generic global function names (Reliability, High)
- **Location:** `narrative()`, `left_overs()`, `display_draw_image()`, `full_report()`, `report_ACT()`.
- **Problem:** all form `report.php` files are included into one scope, so any other form (or `eye_mag_functions.php`) defining the same name causes a fatal "Cannot redeclare".
- **Fix:** prefix them, e.g. `eye_mag_narrative()`.

### 6. Stored XSS: unescaped clinical/user data (Security, High)
These values are echoed raw:
- `$HPI1`
- `$CHRONIC2` and `$CHRONIC3`
- `$item['codetext']`, `$item['code']` and `$item['plan']`
  - `str_replace` to `<br />` is applied without escaping first.
  - Use `nl2br(text(...))` instead.
- `$PLAN` items and `$PLAN2`
- `$note->get_note()`
- `$providerNAME` in the PDF branch
- `$CTLOSVA`
- the `$MOTILITY_*` values
- `$from_file` and `$filetoshow` inside `src` attributes

Wrap them in `text()` or `attr()`.

---

## Medium (correctness)

### 7. Wrong form row can be joined
- **Location:** the `narrative()` and `eye_mag_report()` queries.
- **Problem 1:** neither query filters `forms.formdir='eye_mag'`. `forms.form_id` is only unique per form table, so a vitals or SOAP row with the same `form_id` in that encounter can join to an unrelated `form_eye_mag` row of the same patient.
- **Problem 2:** the queries ignore the `$id` / `$form_id` argument. If an encounter has two eye_mag forms, one is picked arbitrarily.
- **Problem 3:** `narrative()` also drops the `forms.pid` join.
- **Fix:** filter by `form_eye_mag.id = ?` using the passed form id, plus `formdir`.

### 8. `@extract()` of `form_encounter.*` and `form_eye_mag.*`
- **Problem:** this silently overwrites local and parameter variables (`$pid`, `$encounter`, `$form_id`, `$id`, `$choice`…), and `@` hides errors.
- **Fix:** use an explicit array.

### 9. `$choice` is never set
- **Location:** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`
- **Problem:** the check uses a different key case from the assignment.

### 10. Inverted condition in `eye_mag_report()`
- **Location:** `else if ($choice != "narrative")`.
- **Problem:** passing `choice=narrative`, the documented "display everything" value, renders nothing.

### 11. Motility uses `$$zone[$i]`
- **Problem:** PHP 7 parses this as `${$zone}[$i]`, which breaks the loop.
- **Fix:** use `${$zone[$i]}`.

### 12. Motility left-eye table shows the wrong cell
- **Problem:** the bottom row renders `$MOTILITY_LLIO` twice. The first cell should be `$MOTILITY_LRIO`.

### 13. Typos in variable names hide data
- `$ODNEARVA_1||$WNEAROSVA_1` should use `$OSNEARVA_1`.
- `$ODGONIO||$OSDGONIO` should use `$OSGONIO`.
- NPC is gated on `$ODNPC or $OSNPC`, which never exist, but renders `$NPC`. NPC therefore never shows.
- The refraction block is gated on `$ODVA||$OSVA`, which are undefined; the wearing values are `$ODVA_1`. Current Rx is hidden unless AR/MR/CR/CTL data exists.
- The Retina gate omits all OS fields except `$OSDISC`, so OS-only findings are not displayed.

### 14. Autorefraction block uses `${"COMMENTS_$i"}` after the loop
- **Problem:** `$i` is now `count_rx + 1`, so the value is meaningless.

### 15. Debug output in the refraction header
- **Location:** `xlt('Type').$count_rx`.
- **Problem:** it prints the Rx count next to the label.

### 16. Header and data column counts disagree
- **Problem:** the header has 10 columns, but the title row is `colspan="9"`.

### 17. `$RX_TYPE` carries over between rows
- **Problem:** it is not reset per row, so an unknown or empty type shows the previous Rx's type.

### 18. Malformed HTML from conditional tags
- **Location 1, ACT:** `</tr><tr>` is emitted only inside `if ($ACT5CCDIST)`.
- **Location 2, Pupils:** the closing `</td>` is only emitted inside the size branch. With `PUPIL_NORMAL` and no sizes, the `<td>` is left open.
- **Problem:** html2pdf is strict and will mis-render or fail.

### 19. Undefined variables
- `$IMPPLAN_items` is uninitialized; `foreach` warns when there are no rows.
- `$bad` is uninitialized.
- `$css_header` is not global inside `narrative()`, so the stylesheet `href` is empty.
- `$display_Add` is undefined.

### 20. Misleading "electronically signed" output
- **Problem:** in PDF mode, a stored signature image is stamped with "electronically signed on <today>". This is not tied to any actual e-sign event, which is a clinical/legal accuracy concern.

### 21. Patient photo query is nondeterministic
- **Problem:** it uses `SELECT *` across three tables with no `ORDER BY`, so an arbitrary photo is chosen.
- **Fix:** select `documents.id` explicitly and order by date.

### 22. Facility SQL built by concatenation
- **Location:** `"... where id=" . $_SESSION['pc_facility']`.
- **Fix:** use a bound parameter.

---

## Low / Maintainability

- **Dead code to remove:**
  - `left_overs()` uses undefined `$table_name` and `$id`.
  - `full_report()` has unreachable code after `return;`.
  - There is a large commented-out DRAW block.
  - The `else` branch of `display_draw_image()` computes `$filetoshow` and never uses it.
- **Untranslated strings:**
  - "Full to CF OU"
  - "Orders/Next Visit:"
  - "Comments:" in the AR block
- **Broken translation key:** `'sc Near{{without correction near'` is missing its closing `}}`.
- **Red Desaturation title:** `<?php xla(...) ?>` is missing `echo`.
- **Duplicated logic:** document path resolution is copy-pasted from `custom_report.php`. In PDF mode the couch temp file is never actually fetched, so the image path may not exist.
- **Invalid markup:** `<table style="report_vitals" style=...>` has a duplicate `style` attribute (it should be `class`). `heght=75` is a typo. CSS lengths are missing units (`margin:1 auto`, `padding:0 5`).
- **Unnecessary includes:** `globals.php` and the libraries are re-included from a file that is itself included.