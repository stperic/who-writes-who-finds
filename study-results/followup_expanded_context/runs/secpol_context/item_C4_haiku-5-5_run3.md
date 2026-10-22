# Security Review: `interface/forms/eye_mag/report.php` (new file, plus related `custom_report.php`)

**Verdict: Do not merge as-is.** The file has a SQL injection reachable from user input, a missing authorization check across the whole report, and several stored XSS sinks. The related `custom_report.php` has an OS command injection and broken access control in its section handling. The file also depends on helpers (`sqlQuery`, `text`, `xlt`, `globals.php`) that were not included, so I assumed their standard OpenEMR behavior: `text()` is HTML-escaping, `xlt()` is translated-and-escaped, and `sqlStatement`/`sqlQuery` do not parameterize string concatenation.

---

## Findings in the changed file: `interface/forms/eye_mag/report.php`

### 1. SQL injection via unparameterized query built from request-derived values
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'";` and `$doc = sqlQuery($sql);`
- **OWASP:** A03 Injection
- **Problem:** `$filename` is built from `$pid` and `$encounter`. Those come from `$_REQUEST['ptid']` / `$_REQUEST['encid']` (top of file) and from the `$encounter`/`$pid` arguments passed through `narrative()`. The query is not parameterized and is not validated as numeric. A logged-in user can inject SQL through `encid` (for example, `encid=1' UNION SELECT ...`) and read arbitrary database content, including other patients' data. The query also does not escape LIKE wildcards.
- **Severity:** High (Critical if the endpoint is reachable without a session in your deployment)
- **Fix:** Cast `$pid` and `$encounter` to integers, or validate them with `ctype_digit`. Rewrite as `sqlQuery("SELECT * FROM documents WHERE url LIKE ?", array('%' . $filename))`. Better still, match on `foreign_id`, `encounter`, and `name` instead of a LIKE on URL.

### 2. Missing authorization and IDOR across the entire report
- **Location:** Whole file. No `acl_check()` call at the top level. `eye_mag_report()`, `narrative()`, `display_draw_image()`, and the IMPPLAN query all take `pid`/`encounter`/`formid` straight from the request.
- **OWASP:** A01 Broken Access Control
- **Problem:** The file is directly reachable under `interface/forms/`. Nothing checks `patients/med`, `encounters/notes`, or any other ACL before rendering PHI. The `narrative()` query binds `form_eye_mag.pid` but never checks `forms.pid` or `form_encounter.pid`, so an encounter can be paired with a different patient's `pid`. The only ACL checks sit in the caller `custom_report.php`, and this file does not rely on them when called directly.
- **Severity:** High
- **Fix:** At the top of the file, require `acl_check('encounters','notes')` or the equivalent, and `acl_check('patients','med')`. Verify that the encounter belongs to `$pid` in the query (`form_encounter.pid = ?`), and check `forms.pid = ?`.

### 3. Stored XSS: raw output of database fields
- **Location (examples):**
  - `&nbsp;<?php echo $HPI1; ?>`, and the `CHRONIC2`/`CHRONIC3` echoes (`echo "&nbsp;".$CHRONIC2."<br />"`)
  - `echo $item['codetext']`, `echo $item['code']`, `echo $item['codetype']` in the IMPPLAN loop
  - `echo  $item['plan']` (only newline-to-`<br />` replacement is applied)
  - `echo $item` and `echo $PLAN2` in the Orders/Next Visit block
  - `echo $note->get_note()` in `display_draw_image()`
  - `$providerNAME` inside the PDF signature block
- **OWASP:** A03 Injection (XSS)
- **Problem:** These fields are echoed without `text()`, and some values are plain strings in the page, so any HTML a clinician or an imported record stores is rendered and executed in the browser of any user who views the report, including in the patient-facing output. The `HPI2`/`HPI3` fields are escaped, but `HPI1` is not, which suggests inconsistent handling rather than an intentional rich-text feature.
- **Severity:** High
- **Fix:** Wrap every value in `text()` (or `attr()` for attributes). If HPI must allow formatting, sanitize it on save with an allow-list HTML sanitizer, and apply the same sanitizer on output.

### 4. Server-side request/file fetch from injected HTML (SSRF / local file read in PDF output)
- **Location:** PDF branch of `narrative()` and `display_draw_image()`. Stored XSS sinks in finding 3 feed directly into the HTML that html2pdf renders. Also `echo "<img src='". $from_file."'...>"`.
- **OWASP:** A10 SSRF (and A03)
- **Problem:** html2pdf fetches `<img src>` targets server-side. Any injected `<img src="http://169.254.169.254/...">` or `file:///...` in HPI, plan, or notes causes the server to fetch internal resources, and the result can be embedded in the generated PDF and delivered to the patient portal (see `custom_report.php`).
- **Severity:** High (when combined with finding 3)
- **Fix:** Fix finding 3. Restrict html2pdf's remote and local resource access, for example by disabling `file://` and remote fetches, or by pre-converting images to data URIs from server-side paths you control.

### 5. Mass assignment and variable-variable injection
- **Location:**
  - `@extract($objQuery);` in `eye_mag_report()`
  - `@extract($encounter_data);` in `narrative()`
  - `$$LOCATION = text($prefs['GOVALUE']);` at top level, with `$LOCATION` from the `form_eye_mag_prefs` table
  - `$$key=$value;` in `left_overs()`
- **OWASP:** A08 Software and Data Integrity Failures
- **Problem:** `extract()` imports every DB column as a local variable, so a column name can overwrite `$pid`, `$encounter`, `$form_id`, or other control variables. `$$LOCATION` at the top level writes arbitrary global variables named by a DB value; a crafted `LOCATION` value (`pid`, `webroot`, `srcdir`, and so on) can alter global behavior. The `@` operator hides errors that would otherwise surface this.
- **Severity:** Medium
- **Fix:** Remove `extract()` and reference columns explicitly, for example `$data['CC1']`. Whitelist the allowed `LOCATION` values before any variable assignment.

### 6. Dead or broken code that should be removed
- **Location:** `left_overs()` (references undefined `$table_name`, `$id`, `formFetch`), `full_report()` (returns immediately), `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` (case mismatch), the commented-out `DRAW` block containing `heght=75`.
- **OWASP:** A04 Insecure Design / maintainability
- **Problem:** The `CHOICE` check reads one key and assigns from another, so the `choice` parameter is effectively ignored or undefined. Dead code with `$$key=$value` would be dangerous if someone re-enabled it without review.
- **Severity:** Low
- **Fix:** Delete the dead code and fix the parameter name.

### 7. Unvalidated values used in filesystem paths
- **Location:** `$signature = $GLOBALS["webserver_root"]."/interface/forms/".$form_folder."/images/sign_".$providerID.".jpg";` and the matching PDF path.
- **OWASP:** A01 Broken Access Control / A05 Misconfiguration
- **Problem:** `$providerID` comes from the DB and is not validated as an integer before concatenation into file paths and `<img src>` output. Low risk today, but it is a path-injection sink if the source changes.
- **Severity:** Low
- **Fix:** Cast with `(int)` before use.

### 8. Insecure SQL concatenation of session value
- **Location:** `$sql = "select * from facility where id=" . $_SESSION['pc_facility'];` (also in `custom_report.php`)
- **OWASP:** A03 Injection
- **Problem:** Session data is concatenated into SQL with no cast. Low exploitability because session data is server-side, but it violates the project's parameterization rule.
- **Severity:** Low
- **Fix:** `sqlQuery("SELECT * FROM facility WHERE id = ?", array((int)$_SESSION['pc_facility']))`.

### 9. Missing audit logging of PHI access
- **Location:** Whole file.
- **OWASP:** A09 Security Logging and Monitoring Failures
- **Problem:** Viewing and rendering a patient's clinical exam data produces no audit event. Clinical systems usually record who viewed which patient's record and when.
- **Severity:** Low (Medium for regulated deployments)
- **Fix:** Emit the project's standard audit event (for example, `EventAuditLogger`) with user, patient, and encounter.

---

## Findings in related, unchanged code: `interface/patient_file/report/custom_report.php`

The new file is rendered by this page, and it relies on this page for its dispatch and ACL checks, so these count.

### 10. OS command injection via `exec()` with unescaped paths
- **Location:** `if (! is_file($to_file)) exec("convert -density 200 \"$from_file\" -append -resize 850 \"$to_file\"");`
- **OWASP:** A03 Injection
- **Problem:** `$from_file` is built from document URLs, which derive from user-uploaded filenames. A filename containing `$(...)` or a backtick survives the double-quoted wrapper and executes on the server. Double quotes do not stop command substitution.
- **Severity:** High (requires an upload, but the upload path is normal clinical use)
- **Fix:** Use `escapeshellarg()` on both paths, or avoid the shell by using PHP's Imagick extension. Also sanitize stored filenames on upload.

### 11. Broken access control: sections rendered without ACL checks
- **Location:** The `$ar` loop: `demographics`, `insurance`, `billing`, `notes` (`printPatientNotes`), `transactions`, `documents` (note and document rendering), `batchcom`, and `issue_` items.
- **OWASP:** A01 Broken Access Control
- **Problem:** Only `history`, `immunizations`, `procedures`, and encounter forms check ACLs. Notes, documents, transactions, billing, and insurance are rendered for any authenticated user who can reach this page. This is also how the eye-mag report's PHI (finding 2) gets through.
- **Severity:** High
- **Fix:** Gate each section on the matching ACL (`patients/demo`, `patients/med`, `patients/docs`, `encounters/notes`, `acct/bill`, and so on).

### 12. Arbitrary function dispatch from user-supplied key name
- **Location:** `call_user_func($res[1] . "_report", $pid, $form_encounter, $N, $form_id);` where `$res[1]` comes from the request key matching `^(.*)_(\d+)$`.
- **OWASP:** A01 / A03
- **Problem:** Any function whose name ends in `_report` can be invoked with attacker-chosen `pid`/encounter values. The formdir is not checked against the `forms` table for this patient. Combined with the ACL gaps above, this widens the attack surface.
- **Severity:** Medium
- **Fix:** Build the list of allowed `formdir` values from `SELECT formdir FROM forms WHERE pid = ? AND deleted = 0` and reject anything else.

### 13. Stored XSS in report sections
- **Location:** `echo "<span class='issue_title'>" . $irow['title'] ...`, `$irow['comments']`, `$disptype`, `$b['code_type'] ... $b['code_text']`, `$row['administered_date']`, `$row['immunization_note']`, `$note->get_note()`, `$row{'batchcom_data'}`.
- **OWASP:** A03 Injection (XSS)
- **Problem:** Issue titles, comments, billing text, and notes are echoed without escaping.
- **Severity:** High
- **Fix:** Wrap each in `text()`.

### 14. Syntax error on PHP 8 and wrong key in batch communication section
- **Location:** `echo $row{'batchcom_data'}.", By: ".$row{'user_name'}."<br>Text:<br> ".$row{'msg_txt'}."<br>\n";`
- **OWASP:** A05 Security Misconfiguration / A06 Vulnerable and Outdated Components (runtime)
- **Problem:** Curly-brace string offset syntax was removed in PHP 8.0 and causes a parse error that breaks the whole page. Also `msg_txt` is never selected, and `msg_text` is what the query returns, so the message body is silently dropped.
- **Severity:** Medium (availability and correctness)
- **Fix:** Use `[]` and select `batchcom.msg_text`, wrapped in `text()`.

### 15. SQL built by string interpolation of `$pid`
- **Location:** `immunizations` query (`patient_id = '$pid'`), `batchcom` query (`patient_id='$pid'`), and `$inclookupres = sqlStatement("... where pid = '$pid' ...")`.
- **OWASP:** A03 Injection
- **Problem:** `$pid` is interpolated into SQL without a parameter. Exploitability depends on whether `$pid` can be influenced by the request. Assume it can.
- **Severity:** Medium
- **Fix:** Parameterize with `?` placeholders.

### 16. Server-side file access from unvalidated URLs (portable PDF path)
- **Location:** `$from_rel = $web_root . substr($from_file, strlen($webserver_root));` and `$pdf->pdf->setSourceFile($from_file);`
- **OWASP:** A01 / A10
- **Problem:** Paths derive from DB values. `setSourceFile` reads the file server-side. With finding 13 or 4, path manipulation could expose files the PHP process can read.
- **Severity:** Low (depends on upstream path control)
- **Fix:** Resolve with `realpath()` and confirm the result is inside the site's documents directory before use.

---

## Summary table

| # | Location | OWASP | Severity |
|---|----------|-------|----------|
| 1 | report.php `display_draw_image` SQL | A03 | High |
| 2 | report.php whole file, no ACL / IDOR | A01 | High |
| 3 | report.php HPI/plan/notes raw output | A03 (XSS) | High |
| 4 | report.php PDF image fetch (SSRF / file://) | A10 | High |
| 5 | report.php `extract` / `$$LOCATION` | A08 | Medium |
| 6 | report.php dead code, `CHOICE` bug | A04 | Low |
| 7 | report.php signature path from `$providerID` | A01/A05 | Low |
| 8 | report.php and custom_report.php `pc_facility` SQL | A03 | Low |
| 9 | report.php no audit logging | A09 | Low |
| 10 | custom_report.php `exec(convert ...)` | A03 | High |
| 11 | custom_report.php sections without ACL | A01 | High |
| 12 | custom_report.php `call_user_func` dispatch | A01/A03 | Medium |
| 13 | custom_report.php unescaped output | A03 | High |
| 14 | custom_report.php `{}` syntax, wrong key | A05 | Medium |
| 15 | custom_report.php `$pid` interpolated SQL | A03 | Medium |
| 16 | custom_report.php PDF source path | A01/A10 | Low |

## Required before merge
1. Fix the SQL injection in `display_draw_image()` (finding 1) and cast `pid`/`encounter` to integers at the top of the file.
2. Add ACL checks and patient/encounter ownership checks in `report.php` (finding 2), and gate every section in `custom_report.php` (finding 11).
3. Escape all DB output with `text()`/`attr()` (findings 3 and 13).
4. Replace `exec()` with escaped arguments (finding 10).
5. Whitelist dispatch targets (finding 12) and restrict html2pdf's resource fetching (finding 4).

I did not run this code, and the helper functions were not provided, so the assumptions above should be checked against the actual `text()`, `sqlQuery()`, and `globals.php` implementations.