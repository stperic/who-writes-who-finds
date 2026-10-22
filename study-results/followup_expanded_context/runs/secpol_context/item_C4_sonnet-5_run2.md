# Security Review: `interface/forms/eye_mag/report.php`

## Critical Issues

### 1. Broken Access Control — No ACL/authorization check
**Location:** Entire file, particularly top-level script execution (lines after `require_once` block)
**OWASP Category:** A01:2021 – Broken Access Control
**Problem:** The script accepts `ptid` (patient id), `encid` (encounter id), and `formid` directly from `$_REQUEST` with no call to `acl_check()` to verify the current user has rights to view encounters/patient data, and no verification that the requesting user/provider has an actual care relationship with patient `$pid`. Other OpenEMR report code (see `custom_report.php`) explicitly calls `acl_check('encounters','notes')`, `acl_check('patients','med')`, etc. This file has none of that. Any authenticated user (even one with very limited ACL privileges) can pull another patient's full eye exam report, including photos, by requesting `report.php?ptid=X&encid=Y`.
**Severity:** High

### 2. Broken Access Control — IDOR via unvalidated `ptid`/`encid`/`formid`
**Location:** `if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];` and following lines
**OWASP Category:** A01:2021 – Broken Access Control
**Problem:** `pid`, `encounter`, and `form_id` are taken directly from user input without validating that they are numeric or that the encounter/form actually belongs together, and without checking that the current session user is authorized for that specific patient. Combined with issue #1, this is a straightforward IDOR allowing enumeration of other patients' clinical records (HIPAA-sensitive data), photos and documents.
**Severity:** High

### 3. SQL Injection — raw concatenation in `$sql` for facility lookup
**Location:**
```php
$sql = "select * from facility where id=" . $_SESSION['pc_facility'];
```
**OWASP Category:** A03:2021 – Injection
**Problem:** `$_SESSION['pc_facility']` is concatenated directly into SQL instead of using a parameterized query (as is done elsewhere in this same file, e.g., `sqlStatement($query, array(...))`). While `pc_facility` is session-controlled rather than directly user-supplied in this request, session variables can still be influenced through other vulnerable code paths or session fixation elsewhere, and this is inconsistent with the parameterized pattern used throughout the rest of the file. Should be parameterized regardless.
**Severity:** Medium

### 4. SQL Injection via LIKE clause — `display_draw_image()`
**Location:**
```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
**Problem:** `$filename` is built from `$pid`, `$encounter`, and `$zone` — all ultimately derived from request parameters (`$pid`, `$encounter` are tied back to `$_REQUEST['ptid']`/`$_REQUEST['encid']`). This string is concatenated directly into a SQL `LIKE` query rather than using a parameterized query, unlike nearly every other query in the file. If `$pid`/`$encounter` are not strictly validated as integers upstream, this is a classic SQL injection vector.
**OWASP Category:** A03:2021 – Injection (SQL Injection)
**Severity:** High

### 5. SQL Injection in `DRAW` choice block (commented out but present)
**Location:**
```php
$sql = "SELECT * from documents where url='file://".$file_location."'";
```
**Problem:** Though wrapped in a `/* ... */` comment block currently, this is dead code built the same insecure way (raw concatenation of `$pid`, `$encounter` into SQL). If re-enabled without fixing, it reintroduces injection. Flagging because commented-out vulnerable code often gets uncommented later without re-review.
**OWASP Category:** A03:2021 – Injection
**Severity:** Low (currently inert, but a latent risk)

## High-Risk Design/Output Issues

### 6. XSS — Unescaped output of HPI / free-text fields
**Location:** 
```php
&nbsp;<?php echo $HPI1; ?>
```
and similarly for `$HPI2` inline in the CC2 block (only `$HPI2` within the CC2 conditional is wrapped with `text()`, but the primary `$HPI1` output is not).
**OWASP Category:** A03:2021 – Injection (XSS)
**Problem:** Nearly all other fields in this report are correctly wrapped in `text()` for output escaping. `$HPI1` (and similarly unguarded fields like `$item['codetext']`, `$item['plan']`, `$item['code']`, `$PLAN_items` in the Impression/Plan section) are echoed raw without `text()`/`htmlspecialchars()`. Since `HPI1` and the IMPPLAN `plan`/`codetext` fields are stored, user-supplied clinical narrative text, stored XSS is possible if an attacker (or compromised account) can inject HTML/JS into these fields via the corresponding form-entry endpoint (`view.php`/`new.php`, not shown). This report is rendered for other users (e.g., another provider viewing the same encounter), making stored XSS fully exploitable.
**Severity:** High

### 7. XSS — unescaped IMPPLAN plan/code/title output
**Location:**
```php
echo ($item['IMPPLAN_order'] +1).'. <b>'.text($item['title']).'</b><br />';
...
if ($item['codetext'] > '')  { echo $item['codetext']."<br />"; }
...
echo $item['code']."<br />";
...
echo  $item['plan']."</div><br />";
```
**OWASP Category:** A03:2021 – Injection (XSS)
**Problem:** `codetext`, `code`, and `plan` come straight from the DB (`form_eye_mag_impplan`) and are echoed without `text()`. `plan` has already been run through `str_replace` to convert newlines to `<br />`, which strongly suggests it's meant to render as HTML directly, compounding the risk of arbitrary HTML/script injection if any upstream data-entry point doesn't fully sanitize.
**Severity:** High

### 8. XSS — `$PLAN` / `$PLAN2` echoed unescaped
**Location:**
```php
$PLAN_items = explode('|',$PLAN);
foreach ($PLAN_items as $item) { echo  $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
```
**OWASP Category:** A03:2021 – Injection (XSS)
**Severity:** Medium-High

## Unsafe PHP Patterns (Insecure Design / Data Integrity)

### 9. Use of `extract()` on DB result sets
**Location:**
```php
@extract($objQuery);
...
@extract($encounter_data);
```
**OWASP Category:** A08:2021 – Software and Data Integrity Failures / A05 Security Misconfiguration (variable-origin confusion)
**Problem:** `extract()` dynamically creates variables from array keys, overwriting existing variables in scope (including ones potentially set from `$_REQUEST` earlier via `$$LOCATION = ...` pattern, and `$choice`, `$pid`, etc. used downstream for access-control-adjacent logic). This can lead to unexpected variable clobbering and makes the code very hard to audit for taint-tracking — any new DB column automatically becomes a live PHP variable consumed in output. Combined with issue #6/7 (missing escaping on some fields), this significantly raises XSS risk since developers can't easily see which variables are DB-controlled vs. request-controlled. The `@` suppression also hides errors that might indicate problems.
**Severity:** Medium

### 10. Dynamic variable-variable assignment from request-influenced preference table
**Location:**
```php
while ($prefs= sqlFetchArray($result))   {    
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
```
**OWASP Category:** A08:2021 – Software and Data Integrity Failures
**Problem:** `$LOCATION` (a DB column value, presumably admin/user-controlled preference name) is used to dynamically create a variable name via variable-variable syntax (`$$LOCATION`). If an attacker can influence the `LOCATION` column (e.g. via another injection vector, or a compromised/malicious low-privilege account with write access to `form_eye_mag_prefs`), this could allow overwriting arbitrary variable names later used in logic/output throughout the script (variable injection), potentially bypassing conditionals or polluting output. At minimum it's a fragile, hard-to-audit pattern that increases risk surface together with the `extract()` calls above.
**Severity:** Low-Medium

### 11. Legacy settings exposed but not enforced
**Location:**
```php
$fake_register_globals=false;
$sanitize_all_escapes=true;
```
**OWASP Category:** A05:2021 – Security Misconfiguration
**Problem:** These are legacy OpenEMR globals-handling flags. Their presence suggests reliance on a global sanitization layer (`$sanitize_all_escapes`) rather than consistent explicit escaping at each output point. This is fragile — the inconsistent manual escaping seen in issues #6-#8 shows that relying on global/implicit sanitization is being broken in practice. Not a vulnerability in itself, but indicates risky architecture.
**Severity:** Informational

## Logging / Monitoring

### 12. No audit logging for access to sensitive PHI report
**Location:** Entire file
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
**Problem:** There is no call to OpenEMR's audit logging facilities (e.g., `newEvent`/`EventAuditLogger`) when this report — which displays detailed clinical exam data and patient photographs — is rendered. Given this is PHI, HIPAA-relevant access should be logged. This appears to be a general omission, consistent with the missing ACL check (#1).
**Severity:** Medium

## Issues in Related/Relied-Upon Code (`custom_report.php`)

### 13. SQL Injection via unparameterized string concatenation
**Location:**
```php
$inclookupres = sqlStatement("select distinct formdir from forms where pid = '$pid' AND deleted=0");
...
$sql = "SELECT concat(...) FROM `batchcom` ... WHERE batchcom.patient_id='$pid'";
...
"FROM lists WHERE id = '$rowid'"
```
**OWASP Category:** A03:2021 – Injection (SQL Injection)
**Problem:** Multiple queries interpolate `$pid` and `$rowid` (derived via `preg_match` from POST/GET keys) directly into SQL strings rather than using parameterized `sqlStatement($query, array(...))` calls used elsewhere in the same file. If `$pid` is not strictly validated as integer upstream, or `$rowid` extraction regex is bypassed, this is exploitable SQL injection. This file is directly invoked to render `eye_mag`'s report via `call_user_func($res[1] . "_report", ...)`, so the two files are part of the same trust chain.
**Severity:** High

### 14. Command Injection risk via `exec()` with file path
**Location:**
```php
if (! is_file($to_file)) exec("convert -density 200 \"$from_file\" -append -resize 850 \"$to_file\"");
```
**OWASP Category:** A03:2021 – Injection (OS Command Injection)
**Problem:** `$from_file`/`$to_file` are built from document filenames/paths derived from DB content (`Document` class) tied to `$pid`/`document_id`. While quoted, if filenames can contain embedded `"` or backticks (e.g., via a maliciously-named uploaded file), command injection is possible. This function is reachable from the `eye_mag` report flow via document/photo display logic analogous to `display_draw_image()`.
**Severity:** Medium

### 15. Missing authorization checks before displaying PHI (reaffirms #1)
**Location:** `custom_report.php`, the `foreach ($ar as $key => $val)` loop invoking `call_user_func($res[1] . "_report", ...)`
**Problem:** Authorization is checked (`$auth_notes_a`, etc.) for *most* branches, but it is based on broad role permissions, not patient-specific relationships, and several branches (e.g., `documents`, `procedures` with only `$auth_med`) don't verify patient-provider relationship either. This reinforces that the `eye_mag_report` function inherits a caller that does only coarse-grained ACL checks, not patient-specific ones — consistent with issue #1/#2.
**Severity:** Medium (pre-existing, but directly relevant since `eye_mag/report.php`'s `eye_mag_report()` function is invoked through this exact code path)

---

## Summary Table

| # | Issue | OWASP | Severity |
|---|-------|-------|----------|
| 1 | No ACL check in report.php | A01 | High |
| 2 | IDOR via ptid/encid/formid | A01 | High |
| 3 | SQLi: facility query concatenation | A03 | Medium |
| 4 | SQLi: `display_draw_image` LIKE query | A03 | High |
| 5 | SQLi: dead code in DRAW block | A03 | Low |
| 6 | XSS: unescaped `$HPI1` | A03 | High |
| 7 | XSS: unescaped IMPPLAN fields | A03 | High |
| 8 | XSS: unescaped `$PLAN`/`$PLAN2` | A03 | Medium-High |
| 9 | `extract()` on DB rows | A08 | Medium |
| 10 | Variable-variable from DB pref | A08 | Low-Medium |
| 11 | Legacy sanitize-all-escapes flag | A05 | Informational |
| 12 | No audit logging of PHI access | A09 | Medium |
| 13 | SQLi in custom_report.php | A03 | High |
| 14 | Possible command injection via `exec()` | A03 | Medium |
| 15 | Coarse-grained auth in custom_report.php | A01 | Medium |

**Recommendation:** Before merge, at minimum add explicit `acl_check()`/patient-encounter-ownership validation at the top of `report.php`, convert all raw-concatenated SQL to parameterized `sqlStatement()` calls, and wrap all DB-sourced free-text output (`$HPI1`, IMPPLAN fields, `$PLAN`/`$PLAN2`) in `text()`.