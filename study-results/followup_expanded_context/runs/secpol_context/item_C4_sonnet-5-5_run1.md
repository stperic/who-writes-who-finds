# Security review: `interface/forms/eye_mag/report.php` (new file)

## Summary

The most serious problems are SQL injection and an object-level authorization gap, and the file also has a large amount of unescaped output (stored XSS). The reviewed `custom_report.php` is what feeds this file its inputs, and it has related flaws. I recommend blocking the merge until at least findings 1–4 are fixed.

---

## 1. SQL injection in `display_draw_image()`
- **Location:** `display_draw_image()`:
  `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **OWASP:** A03 Injection
- **Problem:** `$filename` is built from `$pid` and `$encounter` by string concatenation with no escaping or binding.
  - Called directly, both values come from `$_REQUEST['ptid']` and `$_REQUEST['encid']`, which the script copies into `$pid` and `$encounter`.
  - Via `custom_report.php`, `$form_encounter = $val` is the raw value of an arbitrary GET/POST parameter, and it is passed unsanitized as `$encounter`. This also makes the route reachable from the patient report.
  - `$sanitize_all_escapes = true` does not make these values safe in a concatenated query.
  - An attacker can read arbitrary data, including PHI and credentials, with UNION or blind injection.
- **Severity:** Critical
- **Fix:** Use a bound parameter: `sqlQuery("SELECT * FROM documents WHERE url LIKE ?", array('%'.$filename))`. Also cast `$pid` and `$encounter` to int.

## 2. Broken access control / IDOR: no authorization check on patient, encounter or form
- **Location:** Top of file (`$pid = $_REQUEST['ptid']; $encounter = $_REQUEST['encid']; $form_id = $_REQUEST['formid'];`) and all queries in `narrative()` / `eye_mag_report()`.
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - The request parameters override the session patient (`$pid`).
  - There is no `acl_check` (for example `patients/med` or `encounters/*`) and no check that the encounter or form belongs to that patient.
  - Any authenticated user can read any patient's clinical data, photo and drawings by iterating IDs.
  - `narrative()`'s query does not join `forms.pid` to the patient.
  - `display_draw_image()` selects a document by filename pattern only and then serves it.
  - The `custom_report.php` caller likewise does not check that the encounter value belongs to `$pid`.
- **Severity:** High
- **Fix:** Do not let request parameters override the session `pid`. Verify the ACL, and verify that the encounter and form belong to the patient. Apply `forms.pid = ?` and `deleted = 0` in all queries.

## 3. Reflected XSS via `pid` / `encounter`
- **Location:** `narrative()` (patient photo) and `display_draw_image()`:
  `echo "<img src='".$GLOBALS['webroot']."/controller.php?...&patient_id=$pid&document_id=...`
- **OWASP:** A03 Injection (XSS)
- **Problem:** `$pid` comes from `$_REQUEST['ptid']` and is written unescaped inside a single-quoted attribute. A value such as `x' onerror='...` executes script. The `from_file` / `$url_file` values are also echoed unescaped into `src`.
- **Severity:** High
- **Fix:** Use `attr()` / `urlencode`, and cast `$pid` to int.

## 4. Stored XSS: unescaped output of database and user-entered fields
- **Location:**
  - `narrative()`: `echo $HPI1;`, `$CHRONIC2`, `$CHRONIC3`, `$item['codetext']`, `$item['code']`, `$item['plan']` (only newline replacement, no escaping), `$PLAN` items, `$PLAN2`, `$providerNAME` (PDF branch), `$CTLOSVA`, and `$MOTILITY_*` (user strings prefixed with `-` and echoed raw).
  - `display_draw_image()`: `$note->get_note()`.
- **OWASP:** A03 Injection (XSS)
- **Problem:** Clinical free text, which can be entered by any user, patients through portals, or imports, is rendered into the page without `text()`. The rest of the file escapes these fields, so the omissions look like oversights. The result is script execution in a clinician's session, which allows session hijack and PHI theft.
- **Severity:** High
- **Fix:** Wrap every output in `text()` / `attr()`. For multi-line fields use `nl2br(text(...))` instead of replacing newlines in the raw text.

## 5. Dangerous variable injection (`extract`, variable variables)
- **Location:**
  - `@extract($objQuery)` and `@extract($encounter_data)`.
  - `$$LOCATION = text($prefs['GOVALUE'])` at file scope.
  - `$$zone[$i]`, `${"ODSPH_$count_rx"}`.
- **OWASP:** A04 Insecure Design / A08 Data Integrity
- **Problem:**
  - Database columns and preference rows silently create or overwrite variables. `$$LOCATION` runs at global scope, so a prefs row named `pid`, `encounter` or `css_header` would overwrite security-relevant globals.
  - `extract` of `form_encounter.*` plus `form_eye_mag.*` can clobber function arguments such as `$pid`, `$encounter`, `$id`.
  - Undefined variables are also silently treated as empty.
- **Severity:** Medium
- **Fix:** Read values explicitly from the row arrays. Whitelist variable names, or drop `extract`.

## 6. Related flaws in the caller (`custom_report.php`) that this code relies on
- **Dynamic function call from user input:** `call_user_func($res[1]."_report", ...)` where `$res[1]` comes from a request key. This allows calling any loaded function ending in `_report` with attacker-chosen arguments, and `include_once` of `forms/$formdir/report.php` uses a database value. (Medium, A01/A04) Whitelist against registered forms.
- **Command injection:** `exec("convert -density 200 \"$from_file\" ...")` where the filename derives from stored document URLs. Use `escapeshellarg()`. (Medium–High, A03)
- **Further SQL injection:** `WHERE patient_id='$pid'`, `forms where pid = '$pid'` and `getEncounterDateByEncounter($form_encounter)` receive unsanitized values, and `$pid` is interpolated in several queries. (High, A03)
- **More XSS:** unescaped `$facility[...]`, `$titleres['fname']`, `$irow['title']`, `$irow['comments']`, billing fields and immunization notes. (High, A03)
- **Missing ACL:** The `$auth_*` flags only gate some sections. The per-form `*_report` output is shown if any of several permissions are held, and does not check access to this specific patient or form. (A01)

## 7. SSRF / local file exposure in PDF mode
- **Location:** `if ($PDF_OUTPUT) { echo "<img src='". $from_file."' ...` and the signature path.
- **OWASP:** A10 SSRF / A05 Misconfiguration
- **Problem:** Absolute server filesystem paths are embedded in HTML that html2pdf fetches. Paths derived from document URLs or request values, such as `$encounter` / `$pid` in the couch URL, could point at local files or remote URLs. The paths also disclose the server layout.
- **Severity:** Low–Medium
- **Fix:** Validate that paths stay under the site documents directory, and use `realpath` checks.

## 8. Security logging and monitoring failure
- **Problem:** Access to patient clinical reports, documents and photos is not audit-logged with `newEvent()` or similar, which matters for PHI (HIPAA).
- **OWASP:** A09
- **Severity:** Low–Medium

## 9. Minor and design issues
- `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` has a case mismatch, so the logic is wrong and `$choice` is user-controlled and unvalidated. (Low)
- `$_REQUEST['formname']` overrides `$form_name`. Whitelist it. (Low)
- `"select * from facility where id=" . $_SESSION['pc_facility']` is concatenated, so bind it. (Low)
- Table name built dynamically: `"form_".$form_folder."_impplan"`. It is currently constant, but keep it that way. (Info)
- `rand()` is used for cache-busting only. (Info)