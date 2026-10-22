# Security review: `interface/forms/eye_mag/report.php` (new file)

This file renders PHI (a patient's eye-exam record), and the issues below are mostly in how it handles inputs and output.

## Findings

### 1. SQL injection in `display_draw_image()`
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **OWASP:** A03 Injection
- **Problem:** `$filename` is built from `$pid` and `$encounter` by string concatenation, with no binding.
  - `$pid` and `$encounter` can be overridden from `$_REQUEST['ptid']` and `$_REQUEST['encid']` at the top of the file.
  - The related `custom_report.php` also passes `$form_encounter = $val` into `eye_mag_report`, where `$val` is the raw value of a GET/POST parameter such as `eye_mag_<id>=<payload>`. Its key regex does not restrict the value.
  - Either path lets an authenticated user inject SQL into a query on the `documents` table. That can lead to reading arbitrary data via UNION, or to blind extraction.
- **Severity:** High
- **Fix:** Use `sqlQuery("... WHERE url LIKE ?", array('%'.$filename))`, and cast `$pid` and `$encounter` to int.

### 2. Broken access control: request parameters override session patient and encounter
- **Location:** top of the file:
  ```php
  if ($_REQUEST['ptid'])   $pid = $_REQUEST['ptid'];
  if ($_REQUEST['encid'])  $encounter = $_REQUEST['encid'];
  if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
  ```
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - The trusted session `$pid` is replaced by a client-supplied value, and no ACL check (`acl_check('patients','med')` or similar) is made anywhere in the file.
  - Any logged-in user, including one with no clinical rights, can read the complete eye-exam record, patient photo, drawings and impression/plan for any patient, encounter and form ID.
  - `custom_report.php` also never checks that `$form_encounter` or `$form_id` belongs to `$pid`.
- **Severity:** High
- **Fix:** Remove the request overrides. Use the session pid, enforce ACLs, and verify the form and encounter belong to that patient.

### 3. Cross-patient document disclosure through the LIKE query
- **Location:** `display_draw_image()`
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - The pattern has a leading wildcard (`'%<pid>_<enc>_OU_<zone>_VIEW.jpg'`).
  - pid `1` therefore matches documents of pid `11`, `21`, `101` and so on. The first match found is displayed without checking `foreign_id`.
  - Document IDs `<= 1` are also skipped.
- **Severity:** Medium to High
- **Fix:** Query by `foreign_id = ?` and an exact URL match.

### 4. Reflected XSS through `$pid`
- **Location:** `narrative()` and `display_draw_image()`:
  ```php
  echo "<img src='".$GLOBALS['webroot']."/controller.php?...&patient_id=$pid&document_id=..."
  ```
- **OWASP:** A03 Injection (XSS)
- **Problem:** `$pid` can come straight from `$_REQUEST['ptid']`, and it is concatenated unescaped into a single-quoted HTML attribute. A value like `x' onerror='...` executes script in the session of a clinician following a crafted link.
- **Severity:** High
- **Fix:** Cast `$pid` to int and use `attr()` or `urlencode` on all URL parts.

### 5. Stored XSS: unescaped database content
- **OWASP:** A03 Injection (XSS)
- **Problem:** Most fields are wrapped in `text()`, but the following are echoed raw. They contain free-text clinical input, so a malicious or compromised user can store script that runs for every clinician who views the report.
- **Severity:** High (stored, and it targets privileged users)
- **Locations:**
  - `echo $HPI1;`
  - `$CHRONIC2` and `$CHRONIC3`
  - IMPPLAN `codetext`, `code`, `codetype` and `plan`. `plan` only has newlines converted to `<br />`, and `title` is the only escaped field.
  - `$PLAN` items and `$PLAN2`
  - `$note->get_note()` in `display_draw_image()`
  - `$CTLOSVA`
  - `$providerNAME` in the PDF signature block
  - `$MOTILITY_*` values
  - `$RX_TYPE` (translated strings, low risk)
- **Fix:** Wrap each of these in `text()`. If line breaks are needed, run `nl2br(text($x))`.

### 6. Unsafe use of `extract()` and variable-variables
- **Location:** `@extract($objQuery)`, `@extract($encounter_data)`, `$$LOCATION = text($prefs['GOVALUE'])`, `$$zone[$i]`, `$$ODzone`
- **OWASP:** A04 Insecure Design
- **Problem:**
  - DB column names or values can overwrite local or global variables.
  - The `$$LOCATION` loop writes user-preference values into arbitrary global variable names, which can clobber `$pid`, `$encounter` or `$css_header` if the LOCATION data is ever tampered with.
  - `$css_header` is used unescaped in `attr()`, and `$visit_date` is a global.
- **Severity:** Medium
- **Fix:** Use explicit arrays, or `EXTR_SKIP` with a prefix.

### 7. Unvalidated session value in SQL
- **Location:** `"select * from facility where id=" . $_SESSION['pc_facility']`, also in `custom_report.php`
- **OWASP:** A03 Injection
- **Problem:** Concatenation without binding. The value is session-derived, so exploitation is unlikely, but it is fragile.
- **Severity:** Low
- **Fix:** Use a bound parameter.

### 8. Server filesystem path disclosure and file-path handling
- **Location:** `if ($PDF_OUTPUT) echo "<img src='". $from_file."'..."` and the signature path
- **OWASP:** A05 Security Misconfiguration
- **Problem:**
  - Absolute server paths are emitted into the HTML, and PDF mode hands html2pdf local file paths built from DB values.
  - `$providerID` is concatenated into the signature file path, and nothing here validates it as numeric.
- **Severity:** Low
- **Fix:** Validate the values as numeric and serve images through the controller with ACL checks.

### 9. Related issues in `custom_report.php` (code this change relies on)
- **Dynamic function call from user input**
  - **Location:** `call_user_func($res[1] . "_report", $pid, $form_encounter, $N, $form_id)`, where `$res[1]` comes from a request parameter key.
  - **OWASP:** A03/A04 Injection / Insecure Design
  - **Problem:** The caller controls which `*_report` function runs. It is limited to already-loaded functions, but the form is not checked against the patient or the ACLs.
  - **Severity:** Medium
- **SQL built by concatenation**
  - **Location:** `where pid = '$pid'`, `i1.patient_id = '$pid'`, `batchcom.patient_id='$pid'`, `lists WHERE id = '$rowid'`
  - **OWASP:** A03 Injection
  - **Problem:** `$pid` comes from the session and `$rowid` is digit-only by regex, so this is low risk, but the pattern is poor.
  - **Severity:** Low
- **Command injection**
  - **Location:** `exec("convert -density 200 \"$from_file\" ...")`
  - **OWASP:** A03 Injection
  - **Problem:** `$from_file` is built from a stored document URL and is not escaped (`escapeshellarg`), so a crafted document name could inject shell commands.
  - **Severity:** Medium
- **Unescaped output**
  - **Location:** facility fields, `$irow['title']`, `$irow['comments']`, billing code text, immunization notes, `$note->get_note()`
  - **OWASP:** A03 Injection (XSS)
  - **Severity:** Medium
- **Weak document authorization**
  - **Location:** document inclusion uses `patient_id=` (empty) in the retrieve URL and does not verify that each document belongs to the patient.
  - **OWASP:** A01 Broken Access Control
  - **Severity:** Medium

### 10. No audit logging
- **OWASP:** A09 Security Logging and Monitoring Failures
- **Problem:** PHI access to arbitrary patients via `ptid`/`encid` is not recorded (no `newEvent`/audit call).
- **Severity:** Low to Medium

## Summary

- **Fix before merge:**
  - Remove the `ptid`/`encid`/`formid` overrides and add ACL and ownership checks.
  - Parameterize the `documents` query and tighten its match.
  - Escape all raw echoes (items 4 and 5).
- **Fix soon after:** the remaining items.