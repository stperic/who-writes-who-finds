# Security Review: `interface/forms/eye_mag/report.php` (new file, 2060 lines)

## Summary

This file has a SQL injection, several stored XSS sinks, and missing access control. The SQL injection and the missing patient/encounter authorization are the most serious. The HPI and note-rendering XSS issues are high-severity because the data is clinician- or patient-entered and is rendered to other users. I did not have `globals.php`, `text()`/`xlt()`/`attr()`, `sqlQuery()`, or `Document`/`Note` in the diff, so some findings assume their behavior (for example, that `text()` HTML-escapes). Verify those assumptions.

---

## Findings

### 1. SQL injection via unescaped `$encounter` and `$pid` in `display_draw_image()`
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`. `$filename` is built from `$pid` and `$encounter`, which come from `$_REQUEST['ptid']` and `$_REQUEST['encid']`.
- **Category:** A03:2021 Injection (SQLi)
- **Problem:** The request-derived values are concatenated into raw SQL with no escaping or parameter binding. The `LIKE '%...'` pattern also allows wildcard abuse. The rest of the file uses `?` placeholders correctly, which makes this call stand out. It is called from `narrative()` with `$encounter` and `$pid` directly from the request, so an authenticated user can inject through `encid` or `ptid` and read arbitrary database content (including other patients' data) through blind or UNION-based techniques. Note that `$encounter` is also passed unmodified in `narrative()`'s `display_draw_image` calls.
- **Severity:** High (authenticated, but can exfiltrate the entire database).
- **Fix:** Use `sqlQuery("SELECT * FROM documents WHERE documents.url LIKE ?", array("%".$filename))`, and validate `$pid` and `$encounter` as integers at the top of the file.

### 2. No authorization check on patient or encounter data (broken access control)
- **Location:** Top of file, `$pid = $_REQUEST['ptid']; $encounter = $_REQUEST['encid']; $form_id = $_REQUEST['formid'];`. `acl.inc` is required but `acl_check()` is never called.
- **Category:** A01:2021 Broken Access Control (IDOR)
- **Problem:** Any logged-in user can request any patient's eye exam, prescriptions, images, and notes by changing `ptid`/`encid`/`formid`. No check that the user has `patients/demo` or `encounters` read rights, and no check that the encounter belongs to the patient (the queries use `form_eye_mag.pid=?` but never validate that the requester may see that `pid`). Medical record access is a HIPAA-relevant control.
- **Severity:** High.
- **Fix:** Add `if (!acl_check('patients','demo')) die(xlt('Not authorized'));` (and the encounters ACL). Confirm that `$encounter` belongs to `$pid` before rendering. Read identifiers from `$_GET`/`$_POST` explicitly and cast to int.

### 3. Stored XSS: unescaped HPI fields
- **Location:** `narrative()`, `<?php echo $HPI1; ?>`, `<?php echo text($HPI2); ?>` (note inconsistent), `<?php echo $HPI3; ?>`, and the `HPI` label lines.
- **Category:** A03:2021 Injection (XSS)
- **Problem:** `$HPI1` is echoed raw. `$HPI2` and `$HPI3` are escaped in some places and raw in others (the `HPI` row for CC3 calls `text($HPI3)`, but the CC1 row does not). Any HTML or script stored in HPI1 executes in the viewer's browser, including during PDF/fax rendering and in the encounter summary mouseover.
- **Severity:** High.
- **Fix:** `echo text($HPI1);` (and the same for all HPI fields). If rich text is intended, sanitize with a whitelist HTML purifier on save and on render.

### 4. Stored XSS: unescaped Impression/Plan and plan text
- **Location:** IMPPLAN loop, `echo $item['codetext']."<br />";`, `echo $item['code']."<br />";`, `echo $item['codetype'].": ".$item['code']`, and `echo $item['plan']."</div><br />";`. Also `echo $item."<br />";` in the `$PLAN` loop and `echo $PLAN2."<br />";`.
- **Category:** A03:2021 Injection (XSS)
- **Problem:** The `plan`, `codetext`, `code`, and `PLAN`/`PLAN2` values come from the database (user-entered or from code lookup) and are echoed without `text()`. The `str_replace` only converts newlines to `<br />`; it does not escape HTML. `$item['title']` is escaped, which makes the omission look accidental.
- **Severity:** High.
- **Fix:** Wrap each value in `text()`, and apply `nl2br(text(...))` for multi-line content.

### 5. Stored XSS: note content from Note objects
- **Location:** `display_draw_image()`, `echo '<td>'.$note->get_note().'<br /><br /></td>';`
- **Category:** A03:2021 Injection (XSS)
- **Problem:** Note text is user-entered and echoed raw into the report, which is also rendered in the patient's chart.
- **Severity:** High.
- **Fix:** `echo '<td>'.nl2br(text($note->get_note())).'<br /><br /></td>';`

### 6. Reflected/attribute-context injection via unescaped `$pid` in image URLs
- **Location:** `narrative()` photo block, `$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=..."` echoed into `<img src='...'>`. Same pattern in `display_draw_image()`.
- **Category:** A03:2021 Injection (XSS)
- **Problem:** `$pid` is taken from the request and inserted into an HTML attribute without encoding. The branch runs only when a matching document is found, but the lookup itself can be influenced by the SQL injection in finding 1. Also, `$GLOBALS['webroot']` is used here, while `display_draw_image` uses `$GLOBALS['webroot']` in one place and `$web_root` (global, unused) elsewhere. The inconsistency may produce broken links.
- **Severity:** Medium.
- **Fix:** Cast `$pid` to int, and use `attr()` or `urlencode()` for the URL.

### 7. Unescaped provider name and file paths in PDF output
- **Location:** PDF branch of the signature block: `echo "<img style='width:50mm;' src='$from_file'><hr ...>".$providerNAME."<br />...`. Also `<img src='". $from_file."'>` in both the photo block and `display_draw_image`.
- **Category:** A03:2021 Injection (XSS); A05 Security Misconfiguration (server-side file references)
- **Problem:** `$providerNAME` is echoed raw. `$from_file` is built from document URLs in the database and is inserted unescaped into `src`. The PDF renderer (html2pdf/TCPDF) resolves these as local file paths, which can load arbitrary local files if the URL in the DB is manipulated.
- **Severity:** Medium.
- **Fix:** `text($providerNAME)` and `attr($from_file)`. Validate that `$from_file` resolves inside the documents directory with `realpath()`.

### 8. Variable-variable assignment from database column names (mass assignment/variable overwrite)
- **Location:** Top of file, `$LOCATION = $prefs['LOCATION']; $$LOCATION = text($prefs['GOVALUE']);`. Also `@extract($objQuery)` and `@extract($encounter_data)` in `eye_mag_report()` and `narrative()`.
- **Category:** A08:2021 Software and Data Integrity Failures; A05 Security Misconfiguration
- **Problem:** Column or pref names from the DB are used as PHP variable names. If the `LOCATION` value is `_SESSION`, `GLOBALS`, `pid`, `encounter`, or `authUserID`, the assignment can overwrite request-scoped state, including session data used in access checks. `extract()` on full table rows can overwrite `$pid`, `$encounter`, `$form_id`, and `$choice` with column values. Data from `form_eye_mag_prefs` is not otherwise validated. Inputs are still `text()`-escaped, which limits XSS, but the overwrite risk is still real.
- **Severity:** Medium.
- **Fix:** Use an explicit whitelist of allowed `LOCATION` names, or store prefs in an associative array. Replace `extract()` with explicit variable reads.

### 9. Request parameter inconsistency
- **Location:** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`
- **Category:** A04 Insecure Design (input handling); A09 logging gap (silent)
- **Problem:** The check tests `CHOICE` but reads `choice`. This is probably a bug, and it causes the check to fail silently for lowercase requests. Compounded with `$formname` from `$_REQUEST['formname']` overwriting `$form_name`, the request surface is larger than necessary.
- **Severity:** Low.
- **Fix:** Use `$choice = $_REQUEST['choice'] ?? 'narrative'` with a whitelist (`NARRATIVE`, `TEXT`, `DRAW`). Do not accept `formname` from the request.

### 10. Unsafe SQL concatenation of session value
- **Location:** `narrative()`, `$sql = "select * from facility where id=" . $_SESSION['pc_facility'];`
- **Category:** A03:2021 Injection (SQLi, defense in depth)
- **Problem:** The value is concatenated, not bound. It is session-derived, so exploitation requires session control, but the pattern is unsafe and is easy to copy.
- **Severity:** Low.
- **Fix:** `sqlQuery("SELECT * FROM facility WHERE id=?", array($_SESSION['pc_facility']))`.

### 11. Insecure use of `$_REQUEST` for security-relevant values
- **Location:** Top of file. `$_REQUEST` is used for `ptid`, `encid`, `formid`, `formname`, `choice`.
- **Category:** A01 / A07 (input handling)
- **Problem:** `$_REQUEST` merges GET, POST, and COOKIE. Using it for identifiers allows cookie-based injection of parameters. This is a poor pattern for an endpoint that returns medical data.
- **Severity:** Low.
- **Fix:** Use `$_GET` or `$_POST` explicitly, and validate with `(int)` casts.

### 12. No audit logging of PHI access
- **Location:** `narrative()` and `eye_mag_report()` (no `EventAuditLogger` or equivalent call).
- **Category:** A09:2021 Security Logging and Monitoring Failures
- **Problem:** Viewing a full eye exam with images, prescriptions, and notes produces no audit record in this code path. Failed access attempts (see finding 2) are not logged either.
- **Severity:** Low to Medium (depends on whether the calling page logs access; verify).
- **Fix:** Emit a disclosure/access audit event with user, patient, encounter, and form ID.

### 13. Dead and fragile code with security implications
- **Location:** `left_overs()` references undefined `$table_name`, `$id`, and calls `formFetch()`. `full_report()` contains `return;` before its body. `narrative()` uses `$bad++` on an undefined variable. The `xla()` call in `title="<?php xla(...); ?>"` (Additional Findings) is missing `echo`, so the attribute is empty.
- **Category:** A04 Insecure Design; A05 Security Misconfiguration (maintainability)
- **Problem:** Dead code is harder to audit and easy to re-enable. Undefined variables produce notices that can leak paths in misconfigured environments (`display_errors`).
- **Severity:** Low.
- **Fix:** Remove dead functions. Initialize `$bad = 0`. Add the missing `echo`.

### 14. Global sanitization flags set in file scope
- **Location:** `$fake_register_globals=false; $sanitize_all_escapes=true;` at the top.
- **Category:** A05 Security Misconfiguration (verify)
- **Problem:** These variables are read by `globals.php`. Their behavior depends on that file, which is not in the diff. Setting them per-page makes the sanitization posture hard to reason about, and any page that omits them may behave differently.
- **Severity:** Informational. Verify against `globals.php`.
- **Fix:** Configure these centrally rather than per file.

---

## Recommended Priority

1. **Finding 1 (SQLi)**: fix before merge.
2. **Finding 2 (ACL)**: fix before merge.
3. **Findings 3, 4, 5 (stored XSS)**: fix before merge. Apply `text()`/`nl2br(text())` consistently to every value that is echoed. Consider a lint rule that flags raw `echo $VAR` in `.php` form files.
4. **Findings 6, 7 (reflected/attribute XSS, file path injection)**: fix before merge.
5. **Findings 8–14**: address in this PR or in follow-up tickets.

Also consider running a static analyzer (Psalm taint analysis, or Semgrep with PHP XSS/SQLi rules) against this file, since the volume of template-style echo statements makes manual review error-prone.