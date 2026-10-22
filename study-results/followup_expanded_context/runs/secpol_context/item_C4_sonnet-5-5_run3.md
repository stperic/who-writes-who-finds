# Security review: `interface/forms/eye_mag/report.php`

I found one SQL injection, several broken-access-control and XSS issues, and a few lower-severity problems. Items 6–8 involve code this change relies on, not code it adds.

## 1. SQL injection in `display_draw_image()`
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **OWASP:** A03 Injection
- **Problem:**
  - `$filename` is built from `$pid` and `$encounter`.
  - At the top of the file these are overwritten from `$_REQUEST['ptid']` and `$_REQUEST['encid']` with no validation.
  - `$sanitize_all_escapes = true` means globals.php does no escaping of request data.
  - The query is concatenated, not parameterized, so a request like `encid=1' OR '1'='1...` or a UNION payload reads arbitrary database content.
  - The function is called several times per report, so the injection point is reached on every request.
  - The `LIKE` also treats `%` and `_` in the input as wildcards.
- **Severity:** Critical (the database holds PHI).
- **Fix:**
  - Use bound parameters.
  - Cast `$pid` and `$encounter` to int.
  - Match the document by `foreign_id` or `documents.url` exactly, not by a `LIKE` on a filename suffix.

## 2. Broken access control / IDOR: no authorization check and request-controlled patient and encounter
- **Location:** Top of the file: `if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];` and the equivalent lines for `encid` and `formid`. The same applies throughout `narrative()` and `display_draw_image()`.
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - The script never calls `acl_check()` for patient medical data or encounter notes. It does require `acl.inc`, but never uses it.
  - It trusts the session `$pid` only until a request parameter overrides it.
  - Any authenticated user, whatever their role, can read any patient's clinical report, photograph and drawings by changing `ptid`, `encid` and `formid`.
  - Nothing verifies that the encounter or form belongs to the patient.
  - `display_draw_image()` looks up a document by filename pattern and never checks it belongs to `$pid`.
  - `custom_report.php` does apply ACL checks around form reports, so this file can be reached directly to bypass them.
- **Severity:** High.
- **Fix:**
  - Enforce `acl_check('patients','med')` and the `encounters` ACLs at the top of the file.
  - Do not let request parameters override the session patient.
  - Verify that the encounter and form belong to the patient.

## 3. Stored XSS: unescaped database output
- **OWASP:** A03 Injection (XSS)
- **Locations and problems:** These fields are free text entered by clinicians or patients and are echoed without `text()`, while the neighbouring fields are escaped.
  - `echo $HPI1;`
  - `$CHRONIC2` and `$CHRONIC3`
  - IMPPLAN `codetext`, `code`, `codetype` and `plan`. `plan` only gets newline-to-`<br />` replacement.
  - `$PLAN` items and `$PLAN2`
  - `$note->get_note()` in `display_draw_image()`
  - The `$MOTILITY_*` values (indirect `$$zone[$i]`). The values are prefixed with `-` but not escaped.
  - `$CTLOSVA`, which is not escaped although `$CTLODVA` is.
  - `$providerNAME` in the PDF signature block.
- **Severity:** High. This is stored XSS in an EMR, which allows session theft and actions as a clinician.
- **Fix:** Wrap every output in `text()` or `attr()` as appropriate. For plan fields use `nl2br(text(...))`.

## 4. Reflected XSS via `ptid` and `encid`
- **Location:** `$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=..."` and `echo "<img src='".$filetoshow."'..."`, in both `narrative()` and `display_draw_image()`.
- **OWASP:** A03 Injection (XSS)
- **Problem:**
  - `$pid` comes straight from `$_REQUEST['ptid']` and is inserted unescaped into a single-quoted HTML attribute.
  - A value such as `1' onerror='...` still matches pid 1 in a MySQL numeric comparison (`foreign_id=?`), so the page renders the image tag and the payload executes.
  - Output built from `$from_file` in the PDF branch has the same unescaped construction.
- **Severity:** High.
- **Fix:** Cast to int on input. Use `attr()` or `urlencode` on output.

## 5. Arbitrary variable overwrite: `$$LOCATION` and `extract()`
- **Location:** `$$LOCATION = text($prefs['GOVALUE']);`. Also `@extract($objQuery)` and `@extract($encounter_data)`.
- **OWASP:** A04 Insecure Design / A08 Software and Data Integrity Failures
- **Problem:**
  - The preference loop creates a global variable whose name is the `LOCATION` column value. This can overwrite security-relevant globals such as `$pid`, `$encounter`, `$css_header`, `$PDF_OUTPUT` or `$GLOBALS` helpers if a row can be inserted or modified.
  - `extract()` of database rows into function scope lets column names clobber local variables.
  - The `$$zone[$i]` indirection has the same variable-variable pattern.
- **Severity:** Medium.
- **Fix:** Use an explicit allowlist of keys and access fields through arrays.

## 6. Reliance on unsanitized and unsafe code in `custom_report.php`
- **OWASP:** A03 Injection / A01 Broken Access Control
- **Problems:**
  - `call_user_func($res[1] . "_report", ...)` takes the function-name prefix from a user-supplied request key. Any function ending in `_report` can be invoked with attacker-influenced arguments.
  - The `include_once` of `forms/$formdir/report.php` uses `$formdir` from the database, which is a file-inclusion risk if that table is tampered with.
  - Many queries embed `$pid` and `$rowid` directly, for example `"... where pid = '$pid'"` and `"... WHERE id = '$rowid'"`.
  - Facility, issue title and comments, billing, immunization, notes and document fields are all echoed unescaped (stored XSS).
  - `exec("convert ... \"$from_file\" ...")` is built from a database-derived path. This is a command-injection risk if a path contains `"` or `$()`.
  - Document IDs are not checked against the patient, because `patient_id=` is passed empty.
  - `$_SESSION['pc_facility']` is concatenated into SQL (this pattern is also copied into the new file).
- **Severity:** Medium to High.

## 7. Weak input handling and logic bugs with security impact
- **OWASP:** A04 Insecure Design
- **Problems:**
  - `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` checks one key and reads another, so the intended gating is broken.
  - `$_REQUEST['formname']` overrides `$form_name`, and `$_REQUEST` mixes in cookies.
  - `$document_id > '1'` skips document ID 1.
  - Photo and drawing document lookups do not verify ownership.
- **Severity:** Low to Medium.

## 8. Logging and monitoring
- **OWASP:** A09 Security Logging and Monitoring Failures
- **Problem:** Accessing a patient's clinical report writes no audit entry (for example via `newEvent`). Combined with item 2, unauthorized PHI access would go undetected.
- **Severity:** Low to Medium.

## 9. Filesystem path exposure and PDF generation
- **OWASP:** A05 Security Misconfiguration
- **Problem:** In PDF mode the code emits absolute server filesystem paths into `<img src=...>` tags. If a document URL were attacker-influenced, HTML2PDF would read an arbitrary local file into the output. The paths also expose the server layout.
- **Severity:** Low.

## Priority fixes before merge
1. Parameterize the query in `display_draw_image()` and cast `pid`, `encid` and `formid` to int.
2. Add ACL checks and patient/encounter ownership verification.
3. Escape all unescaped output, especially HPI, plan, impression, notes and the URL parameters.
4. Remove the variable-variable and `extract` patterns, or allowlist them.
5. Add audit logging.