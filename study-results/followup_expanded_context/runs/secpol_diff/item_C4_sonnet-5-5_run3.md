# Security review: `interface/forms/eye_mag/report.php` (new file)

This page renders PHI (patient encounters, exam findings, drawings, photos, signatures). I found missing authorization, a SQL injection, reflected and stored XSS, and several lower-severity issues.

## 1. Broken access control: request-controlled patient, encounter and form IDs, with no authorization check
**Location:** top of file, `if ($_REQUEST['ptid']) $pid = ...; encid; formid; formname`, plus the whole script
**OWASP:** A01 Broken Access Control (also A04 Insecure Design)
**Problem:**
- `$pid`, `$encounter` and `$form_id` are taken directly from `$_REQUEST`, overriding the session's active patient.
- The script never calls an ACL check (for example `acl_check('patients','med')` or `acl_check('encounters', ...)`), although `acl.inc` is included.
- It never verifies that the encounter or form belongs to the given `pid`.
- `narrative()` queries by `form_encounter.encounter` and `form_eye_mag.pid` only. It does not tie `forms.pid` to the request or check the user's right to see that patient.
- Any authenticated user, whatever their role, can enumerate IDs and read other patients' clinical reports, photographs, drawings and notes (IDOR).
- Separately, `$_REQUEST['CHOICE']` is tested but `$_REQUEST['choice']` is read, so the logic is broken. It still shows that request input is trusted without validation.

**Severity:** High

## 2. SQL injection in `display_draw_image()`
**Location:** `display_draw_image()`:
```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```
**OWASP:** A03 Injection
**Problem:**
- `$pid` and `$encounter` come from `$_REQUEST['ptid']` and `$_REQUEST['encid']` and are concatenated into SQL with no parameter binding.
- `$sanitize_all_escapes=true` disables OpenEMR's input escaping, so nothing protects this query.
- An attacker can read or alter the database (credentials, all PHI).
- Even without injection, `_` and `%` are LIKE wildcards. The query is not scoped to the patient, so it can return another patient's document.
- The resulting `$doc['id']` is then passed to `Document` and `controller.php?...retrieve`.

**Severity:** Critical

## 3. Other string-built SQL
**Location:** `narrative()`: `"select * from facility where id=" . $_SESSION['pc_facility']`
**OWASP:** A03 Injection
**Problem:** The session value is concatenated into the query. It is probably server-set, but it should be bound as a parameter. If it is ever influenced by the user, it becomes injectable.
**Severity:** Low

## 4. Reflected XSS through `$pid` and `$encounter`
**Location:** `narrative()` and `display_draw_image()`:
```php
$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=...";
echo "<img src='".$filetoshow."' ...>";
```
**OWASP:** A03 Injection (XSS)
**Problem:**
- `$pid` comes from `$_REQUEST['ptid']` and is echoed into an HTML attribute without `attr()` or `urlencode()`.
- A single quote breaks out of the attribute. For example, `ptid=5' onerror='...` still matches patient 5 in the `foreign_id=?` comparison, because MySQL truncates the string to an integer.
- This gives script execution in a clinician's session via a crafted link.

**Severity:** High

## 5. Stored XSS: unescaped database content
**OWASP:** A03 Injection (XSS)
**Severity:** High, because clinical free text is entered by many users, and patient-supplied data may also reach these fields.

**Location (all echoed raw):**
- `echo $HPI1;`
- `$CHRONIC2`, `$CHRONIC3`
- Impression/Plan items: `echo $item['codetext']`, `$item['code']`, `$item['plan']`. The `str_replace` to `<br />` is applied after the DB read and does not escape anything.
- `$PLAN_items` and `$PLAN2`: `echo $item."<br />"`
- `$note->get_note()` in `display_draw_image()`
- `$CTLOSVA`
- `$MOTILITY_*` values
- `$providerNAME` in the PDF signature block
- `$display_Add`, `$RX_TYPE` and `$form_folder` (the last two come from fixed values, but they are inconsistently escaped)

**Problem:**
- Neighbouring fields use `text()`, so the lack of escaping on these is clearly a mistake. `HPI2` and `HPI3` are escaped while `HPI1` is not.
- A malicious or compromised user, or any upstream data source such as a portal, can store a script that runs for every clinician who opens the report.

**Fix:** Wrap all of these in `text()`, or in `nl2br(text())` where line breaks are needed.

## 6. Variable-variable and `extract()` overwrite of local and global state
**Location:**
- Top of file: `$$LOCATION = text($prefs['GOVALUE']);`
- `@extract($objQuery)` and `@extract($encounter_data)`
- `$$zone[$i]`, `$$ODzone`
- `${"ODSPH_$count_rx"}`

**OWASP:** A04 Insecure Design / A08 Software and Data Integrity Failures
**Problem:**
- The prefs table's `LOCATION` column is used as a variable name at global scope. A crafted pref row can overwrite arbitrary globals (`$pid`, `$encounter`, `$GLOBALS`-derived variables, `$css_header`, `$PDF_OUTPUT`).
- `extract()` on whole DB rows can overwrite function parameters and locals.
- `@` hides errors.

**Severity:** Medium

## 7. Electronic signature images in a web-accessible directory
**Location:** `narrative()`: `interface/forms/eye_mag/images/sign_<providerID>.jpg`
**OWASP:** A05 Security Misconfiguration / A01 Broken Access Control
**Problem:**
- Provider signatures are stored under a statically served web directory with a predictable filename (`sign_<id>.jpg`).
- They are retrievable without authentication and can be enumerated.
- A signature is added to any report automatically, with no check that the provider actually signed or attested.

**Severity:** Medium

## 8. Server filesystem path disclosure
**Location:** `narrative()` and `display_draw_image()`:
```php
echo "<img src='".$from_file."' ...>";   // PDF branch, absolute server path
```
**OWASP:** A05 Security Misconfiguration
**Problem:**
- Absolute paths such as `fileroot/sites/<site>/documents/...` and `webserver_root` are emitted into markup, unescaped.
- The paths are built from document URLs stored in the DB.
- If the output is processed by an HTML-to-PDF library, an attacker-influenced path or URL could cause local file inclusion or SSRF in the renderer.

**Severity:** Low to Medium

## 9. Missing audit logging for PHI access
**Location:** whole file
**OWASP:** A09 Security Logging and Monitoring Failures
**Problem:** There is no `newEvent()` or equivalent audit log when a patient's report, photo or drawings are viewed. Combined with finding 1, unauthorized access would leave no trace.
**Severity:** Low to Medium

## 10. Minor
- **`rand()` cache-busting parameter** is harmless, but `$d->get_couch_url()` and temporary files in `documents/temp/` are used without cleanup or access checks (A05, low).
- **Document and note retrieval** (`Document`, `Note::notes_factory`) is not checked against the patient, so it depends entirely on the unverified `$pid` and document ID (see 1 and 2).

## Summary

| # | Issue | Severity |
|---|-------|----------|
| 2 | SQL injection (`display_draw_image`) | Critical |
| 1 | Missing authorization / IDOR via `ptid`, `encid`, `formid` | High |
| 4 | Reflected XSS via `$pid` in `<img src>` | High |
| 5 | Stored XSS from unescaped fields | High |
| 6 | Variable-variable and `extract` overwrite | Medium |
| 7 | Signatures in a public web directory | Medium |
| 8 | Path disclosure and unescaped paths | Low–Medium |
| 9 | No audit logging | Low–Medium |
| 3 | Concatenated `facility` query | Low |

**Recommendation:** Do not merge until at least findings 1, 2, 4 and 5 are fixed. Use bound parameters everywhere, escape all output with `text()` or `attr()`, and add ACL and ownership checks plus audit logging.