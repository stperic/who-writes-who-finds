## Security review: `interface/forms/eye_mag/report.php` (new file)

The file renders PHI (patient clinical reports), so the access control and output encoding problems matter more than they would elsewhere. The first three findings should block the merge.

---

### 1. SQL injection in `display_draw_image()`
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'"`
- **OWASP:** A03 Injection
- **Problem:**
  - `$filename` is built from `$pid` and `$encounter`.
  - At the top of the file both are overwritten from `$_REQUEST['ptid']` and `$_REQUEST['encid']`.
  - The file sets `$sanitize_all_escapes = true`, so no global escaping is applied, and the values are concatenated into the SQL string.
  - An attacker can inject arbitrary SQL, for example UNION or boolean/time-based extraction of the whole database. LIKE wildcards (`%`, `_`) in the input are also possible.
  - Every other query in the file uses bound parameters, which shows the correct pattern.
- **Fix:** use `sqlQuery("... like ?", array('%'.$filename))` and cast `$pid` and `$encounter` to int.
- **Severity:** Critical

### 2. Broken access control / IDOR: request parameters override the session patient, with no authorization check
- **Location:** top of the file: `if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid']; if ($_REQUEST['encid']) $encounter=...; if ($_REQUEST['formid']) $form_id=...;`
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - The patient, encounter and form IDs come straight from the request and replace the session's `$pid`.
  - There is no `acl_check()` for patient or encounter access, and no check that the encounter or form belongs to the patient.
  - Any authenticated user, regardless of role or care relationship, can read any patient's ophthalmology report, patient photo, drawings and signatures by changing `ptid`, `encid` and `formid`.
  - `narrative()` also does not check `forms.pid`, so IDs can be mixed across patients.
  - `display_draw_image()` looks up documents by filename with no ownership check.
- **Fix:** require an ACL check (for example `acl_check('patients','med')`). Use the session pid, or validate that the requested pid is authorized. Verify that the encounter and form belong to that pid.
- **Severity:** High

### 3. Stored XSS: unescaped database content echoed into HTML
- **Location:** `narrative()` and `display_draw_image()`
- **OWASP:** A03 Injection (XSS)
- **Problem:** Many clinical free-text fields are echoed without `text()`, even though neighbouring fields are escaped. Anyone who can write chart data (or an imported or integrated source) can run script in the browser of every clinician who views the report, enabling session theft and actions as that user. Affected output:
  - `echo $HPI1;`
  - `$CHRONIC2`, `$CHRONIC3`
  - IMPPLAN items: `$item['codetext']`, `$item['code']` (including `codetype`) and `$item['plan']`. The `str_replace` only converts newlines to `<br />`.
  - `$PLAN` items and `$PLAN2`
  - `$note->get_note()` (document notes)
  - `$CTLOSVA`
  - `$providerNAME` in the PDF signature block
  - `$MOTILITY_*` values and `$display_Add`
- **Fix:** wrap each in `text()`, or `nl2br(text())` where line breaks are needed.
- **Severity:** High

### 4. Reflected XSS via `ptid` in image URLs
- **Location:** `narrative()` and `display_draw_image()`, `"...patient_id=$pid&document_id=..."` echoed inside `<img src='...'>`
- **OWASP:** A03 Injection (XSS)
- **Problem:**
  - `$pid` is attacker-controlled (`ptid`) and is inserted unescaped into a single-quoted attribute.
  - A value such as `1' onerror='alert(1)` breaks out of the attribute.
  - The photo lookup is `foreign_id=?`, and MySQL's numeric coercion makes `"1' onerror=..."` match patient 1, so the branch is reached.
- **Fix:** cast `$pid` to int and wrap the URL in `attr()` / `attr_url()`.
- **Severity:** High

### 5. Local file path and server information disclosure in PDF mode
- **Location:** `echo "<img src='". $from_file."' ..."` (photo, drawings, signature)
- **OWASP:** A05 Security Misconfiguration / A01
- **Problem:**
  - Absolute filesystem paths built from DB-derived `$from_pathname` and `$from_filename` are embedded unescaped in HTML for the PDF generator.
  - Paths are not validated against traversal and not escaped.
  - If the document URL or path data is manipulated, the PDF engine may read arbitrary local files.
  - The paths themselves disclose the server layout.
- **Severity:** Medium

### 6. Variable injection and overwrite via `$$LOCATION` and `extract()`
- **Location:**
  - `$$LOCATION = text($prefs['GOVALUE']);` at global scope
  - `@extract($objQuery);` and `@extract($encounter_data);` in `eye_mag_report()` and `narrative()`
  - `${"..._$count_rx"}` dynamic variables
- **OWASP:** A04 Insecure Design / A08 Data Integrity
- **Problem:**
  - Variable names come from DB column values (`LOCATION`) and DB column names. Data can overwrite control variables such as `$pid`, `$encounter`, `$choice`, `$cols`, `$form_id` and `$PDF_OUTPUT`.
  - In `narrative()`, `extract()` of `form_encounter.*` and `form_eye_mag.*` can replace the function parameters `$pid`, `$encounter` and `$form_id` with DB values.
  - A user-controlled `prefs.LOCATION` value could override the `ptid`-derived `$pid`, or other globals.
- **Fix:** read values from the arrays explicitly and use an allow-list of variable names.
- **Severity:** Medium

### 7. SQL built by concatenating a session value
- **Location:** `$sql = "select * from facility where id=" . $_SESSION['pc_facility'];`
- **OWASP:** A03 Injection
- **Problem:** The value is a session value, not directly user input, so exploitability is low. It should still be parameterized or cast.
- **Severity:** Low

### 8. No audit logging of PHI access
- **Location:** whole file
- **OWASP:** A09 Security Logging and Monitoring Failures
- **Problem:** Reports containing PHI (clinical data, photo, signature) are rendered with no `newEvent()` audit entry. Combined with the IDOR in finding 2, snooping on other patients' charts would go undetected.
- **Severity:** Medium

### 9. Weaker items and code quality
- **`$_REQUEST['CHOICE']` / `$_REQUEST['choice']` mismatch:** The condition tests `CHOICE` but reads `choice`, so `$choice` is effectively never set from input and the report mode logic is unreliable. This is a correctness bug, but it makes the intended input handling ambiguous. Use an allow-list for `$choice`. **Severity:** Low
- **Use of `$_REQUEST`:** It merges GET, POST and cookies, which makes CSRF-style linking and cookie-based parameter injection easier. Use `$_GET` or `$_POST` explicitly. **Severity:** Low
- **Predictable `rand()` cache-busters:** There is no security impact. **Severity:** Informational
- **Error suppression with `@extract`:** It hides failures. **Severity:** Informational

---

### Summary
| # | Issue | Severity |
|---|---|---|
| 1 | SQL injection (`display_draw_image`) | Critical |
| 2 | IDOR / missing ACL via `ptid`, `encid`, `formid` | High |
| 3 | Stored XSS (many unescaped fields) | High |
| 4 | Reflected XSS via `ptid` in image URLs | High |
| 5 | File path disclosure / local file handling in PDF mode | Medium |
| 6 | Variable injection (`$$LOCATION`, `extract`) | Medium |
| 8 | No audit logging | Medium |
| 7, 9 | Session-concatenated SQL, `$_REQUEST` use, `$choice` logic | Low |

I recommend not merging until findings 1–4 are fixed.