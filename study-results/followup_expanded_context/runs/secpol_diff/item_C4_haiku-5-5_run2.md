# Security Review: `interface/forms/eye_mag/report.php` (new file)

**Verdict: Do not merge as-is.** The file has a SQL injection, several stored and reflected XSS paths, and no patient-access authorization check. The first three findings are the blockers.

---

## Findings

### 1. SQL injection in `display_draw_image()`
- **Location:** `display_draw_image()`, first query: `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **OWASP:** A03:2021 Injection
- **Problem:** `$filename` is built from `$pid`, `$encounter`, and `$zone`. `$pid` and `$encounter` come from `$_REQUEST['ptid']` and `$_REQUEST['encid']` (set at the top of the file) and are concatenated into raw SQL without escaping or type checks. The query uses `sqlQuery()` with no bind parameters. Most other queries in this file are parameterized, so this one is inconsistent. A `LIKE` pattern also adds wildcard matching, which can match unintended rows.
- **Severity:** High (Critical if the endpoint can be reached without a login)
- **Fix:** Use a bound parameter, e.g. `sqlQuery("SELECT * FROM documents WHERE url LIKE ?", array('%'.$filename))`. Cast `$pid` and `$encounter` to integers or validate them first. Prefer an exact match over `LIKE`.

### 2. Stored XSS: unescaped clinical text in `narrative()`
- **Location:** `narrative()`, multiple sites, including:
  - `echo $HPI1;`, `echo $HPI2;`, `echo $HPI3;` (HPI is printed without `text()`)
  - `if ($CHRONIC2) echo "&nbsp;".$CHRONIC2."<br />";` and the same for `$CHRONIC3`
  - `echo $item['codetext']`, `echo $item['code']`, `echo $item['plan']` in the IMPPLAN loop
  - `echo $PLAN_items` items and `echo $PLAN2`
- **OWASP:** A03:2021 Injection (XSS)
- **Problem:** These fields hold free-text clinician input. They are printed raw, so any `<script>` or event-handler markup saved in an exam form executes for every user who views the report, including the PDF/fax paths. The `str_replace` on `plan` converts newlines to `<br />` but does not escape anything.
- **Severity:** High
- **Fix:** Wrap every output in `text()` (or `attr()` in attributes). Apply escaping first, then convert newlines to `<br />`, e.g. `nl2br(text($plan))`.

### 3. Stored XSS: unescaped note text in `display_draw_image()`
- **Location:** `display_draw_image()`, note loop: `echo '<td>'.$note->get_note().'<br /><br /></td>';`
- **OWASP:** A03:2021 Injection (XSS)
- **Problem:** Note content is user-entered and is output without escaping.
- **Severity:** High
- **Fix:** `echo '<td>' . text($note->get_note()) . '<br /><br /></td>';`

### 4. Reflected XSS / attribute injection via `$pid` in `<img src>`
- **Location:** `narrative()`: `$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=..."` and the matching line in `display_draw_image()`. Both are echoed into `<img src='...'>` with single quotes.
- **OWASP:** A03:2021 Injection (XSS)
- **Problem:** `$pid` is not URL-encoded or HTML-escaped. MySQL's implicit string-to-number conversion means a crafted `ptid` such as `1'><script>...` can still match patient 1's photo row in the `foreign_id=?` lookup, which reaches this echo. This is a reflected XSS path that works through a crafted link.
- **Severity:** Medium-High
- **Fix:** Cast `$pid` to int at input. Build the URL with `urlencode()` and output it with `attr()`.

### 5. Broken access control / IDOR: no patient or encounter authorization
- **Location:** Top of file: `$pid = $_REQUEST['ptid']`, `$encounter = $_REQUEST['encid']`, `$form_id = $_REQUEST['formid']`. No ACL call exists anywhere in the file (`acl_check`, `verifyPatientAccess`, or similar).
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The file renders a full patient's exam, PMH, photo, signature, and plan for whatever IDs are supplied. Any authenticated user can request any patient's report by changing `ptid`/`encid`. The file also reads from `$_REQUEST`, so the parameters can come from GET or POST.
- **Severity:** High
- **Fix:** Check that the user has patient-record access (e.g. `acl_check('patients', 'med')` or the equivalent project check) before rendering. Verify that `$encounter` belongs to `$pid` and that `$form_id` belongs to that encounter. Read input from `$_GET`/`$_POST` explicitly.

### 6. No input validation on identifiers and selectors
- **Location:** `$_REQUEST['ptid']`, `$_REQUEST['encid']`, `$_REQUEST['formid']`, `$_REQUEST['formname']`, `$_REQUEST['choice']`. Also `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` uses mismatched case.
- **OWASP:** A03:2021 Injection / A04:2021 Insecure Design
- **Problem:** Identifiers are not validated as integers. `formname` is assigned straight into the global `$form_name`, which other included code may later use in paths. The `CHOICE`/`choice` mismatch means the guard never matches the value it sets.
- **Severity:** Medium
- **Fix:** Validate with `(int)` or `ctype_digit` and reject anything else. Drop `formname` or whitelist it. Fix the case mismatch.

### 7. Variable-variable and `extract()` pollution of global and local scope
- **Location:**
  - Global scope: `$LOCATION = $prefs['LOCATION']; $$LOCATION = text($prefs['GOVALUE']);`
  - `@extract($objQuery);` in `eye_mag_report()`
  - `@extract($encounter_data);` in `narrative()`
  - `left_overs()`: `$$key=$value;`
- **OWASP:** A08:2021 Software and Data Integrity Failures / A04:2021 Insecure Design
- **Problem:** Names come from database columns (`LOCATION` in the prefs table, which users can write through the form's preferences save). A row whose `LOCATION` is `form_folder`, `pid`, `PDF_OUTPUT`, or a core global can overwrite that variable. Those values later build include paths, output mode, and SQL. `@extract()` likewise imports every column of two joined tables into local scope, so a column name can shadow a variable the code relies on. The `@` operator hides the resulting warnings. `left_overs()` does the same with unvalidated keys.
- **Severity:** Medium
- **Fix:** Remove the variable-variable and `extract()` patterns. Read named columns explicitly, e.g. `$HPI1 = $row['HPI1']`. Whitelist allowed `LOCATION` names if prefs must map to variables.

### 8. Unvalidated file paths and local file references in PDF output
- **Location:** `narrative()` and `display_draw_image()`: `$from_file = $GLOBALS["fileroot"] . "/sites/" . $_SESSION['site_id'] . '/documents/' . $from_pathname . '/' . $from_filename;` and `echo "<img src='". $from_file."'...>"`. Also the signature path `sign_".$providerID.".jpg"`.
- **OWASP:** A01:2021 Broken Access Control / A10:2021 SSRF (local variant)
- **Problem:** `$from_file` comes from `documents.url` in the database. In PDF mode the HTML is rendered by html2pdf, which fetches `<img src>` values. A tampered `url` containing `..` segments or a `file://` scheme can make the renderer read arbitrary local files into the PDF. The signature path also exposes absolute server paths in the output.
- **Severity:** Low-Medium (requires write access to `documents.url`)
- **Fix:** Resolve the real path with `realpath()` and verify it sits under the expected documents root. Reject non-local schemes. Do not emit absolute server paths; embed image data instead.

### 9. SQL built from session value
- **Location:** `narrative()`: `$sql = "select * from facility where id=" . $_SESSION['pc_facility'];`
- **OWASP:** A03:2021 Injection
- **Problem:** The session value is concatenated without type enforcement. The attack surface is small, but the pattern is unsafe.
- **Severity:** Low
- **Fix:** Use a bound parameter or `(int)$_SESSION['pc_facility']`.

### 10. Insecure legacy configuration and error handling
- **Location:** Top of file: `$fake_register_globals=false; $sanitize_all_escapes=true;`. Throughout: `@extract(...)`, and `report_ACT()` uses `htmlspecialchars($term, ENT_NOQUOTES)`.
- **OWASP:** A05:2021 Security Misconfiguration
- **Problem:** These flags are legacy and do not protect the output paths above. `@` suppresses errors that would reveal failed queries. `ENT_NOQUOTES` is not safe for attribute contexts, and `report_ACT()` is used for free-text comments as well as ACT cells, which is misleading.
- **Severity:** Low
- **Fix:** Remove the legacy flags. Use `ENT_QUOTES` in an escaping helper or the standard `text()`/`attr()` helpers. Stop using `@`.

### 11. Audit logging of PHI access
- **Location:** Entire file. No audit or access event is recorded when a report is viewed.
- **OWASP:** A09:2021 Security Logging and Monitoring Failures
- **Problem:** The report discloses sensitive health information with no record of who viewed which patient's data. This matters for HIPAA-regulated deployments.
- **Severity:** Low
- **Fix:** Log a view event (user, patient, encounter, timestamp) through the project's audit logging.

### 12. Dead code with unsafe patterns
- **Location:** `full_report()` (returns immediately, then references undefined `formFetch` and `$table_name`), and `left_overs()` (references undefined `$table_name`, `$id`).
- **OWASP:** A04:2021 Insecure Design
- **Problem:** Unreachable or broken code that uses `$$key=$value` and `print` of unescaped values. It increases review surface and invites copy-paste reuse.
- **Severity:** Low
- **Fix:** Delete it.

---

## Non-security issues noticed during review
- `xla('Variation in red color discrimination ...')` is called inside a `title` attribute without `echo`, so the tooltip is empty.
- `$GLOBALS['webroot']` is used in `narrative()` but `global $web_root` is used in `display_draw_image()`. The naming is inconsistent and may produce broken image URLs.
- `$$zone[$i]` in the motility block is ambiguous under PHP 7+ variable-variable parsing and should be written as `${$zone[$i]}`.
- `$bad < '1'` and similar loose comparisons should be numeric.
- The `style="report_vitals"` attribute is a malformed table tag.

## Not assessable from the diff
- **Vulnerable components:** The file uses Font Awesome 4 classes and html2pdf for PDF output. Versions and known CVEs must be checked against the project's dependency manifest.
- **Cryptography:** None is used in this file. Signature and photo files are served from the filesystem without integrity checks, which is acceptable here but worth noting.

---

## Recommended order of remediation
1. Fix the SQL injection (Finding 1).
2. Add patient and encounter authorization and input validation (Findings 5, 6).
3. Escape all clinical output with `text()`/`attr()`, including notes (Findings 2, 3, 4).
4. Remove variable-variable and `extract()` usage (Finding 7).
5. Harden file path handling and remove dead code (Findings 8, 12).
6. Add audit logging and clean up legacy configuration (Findings 10, 11).