# Security Review – `interface/forms/eye_mag/report.php`

## Critical

### 1. Missing authorization / IDOR on patient data
**Location:** Top of file —
```php
if ($_REQUEST['ptid'])    $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid'])   $encounter = $_REQUEST['encid'];
if ($_REQUEST['formid'])  $form_id = $_REQUEST['formid'];
```
and throughout `eye_mag_report()` / `narrative()`.
**OWASP Category:** A01:2021 – Broken Access Control
**Problem:** There is no call to `acl_check()`, no verification that the logged-in user is authorized for the requested `pid`/`encounter`/`form_id`, and no check that the encounter belongs to the facility/provider the user is permitted to see. Any authenticated user can change `ptid`/`encid`/`formid` in the URL and pull another patient's full eye exam (HPI, photo, prescriptions, impression/plan, physician signature image, drawings). This is a textbook IDOR against ePHI.
**Severity:** Critical

---

## High

### 2. Reflected XSS via unescaped `$pid` in image `src` attributes
**Location:**
```php
$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=".$doc['document_id']."&as_file=false&blahblah=".rand();
echo "<img src='".$filetoshow."' style='width:220px;'>";
```
(same pattern in `display_draw_image()`)
**OWASP Category:** A03:2021 – Injection (XSS)
**Problem:** `$pid` is taken straight from `$_REQUEST['ptid']` and concatenated into an HTML attribute without `attr()`/`htmlspecialchars()`. An attacker can break out of the `src='...'` attribute (e.g. `ptid=1'><script>...`) to inject markup/script. Although `$sanitize_all_escapes` performs a SQL-oriented escape, it does not HTML-encode for output context.
**Severity:** High

### 3. SQL Injection in `display_draw_image()`
**Location:**
```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
**OWASP Category:** A03:2021 – Injection (SQL)
**Problem:** `$pid` and `$encounter` (user-controlled, from `$_REQUEST`) are concatenated directly into a SQL string instead of using the parameterized `sqlStatement()`/`sqlQuery($sql, $params)` pattern used everywhere else in this file. Relying solely on the global `$sanitize_all_escapes` flag for injection defense is fragile and inconsistent with the rest of the codebase.
**Severity:** High

### 4. Dangerous dynamic variable assignment from DB-controlled key (`LOCATION`)
**Location:**
```php
$query  = "SELECT * FROM form_eye_mag_prefs where PEZONE='PREFS' AND id=? ORDER BY ZONE_ORDER,ordering";
$result = sqlStatement($query,array($_SESSION['authUserID']));
while ($prefs= sqlFetchArray($result)) {
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
```
**OWASP Category:** A04:2021 – Insecure Design (variable-variable / "poor man's register_globals")
**Problem:** The variable name to assign is taken from a database column (`LOCATION`) and used in a variable-variable (`$$LOCATION`). If that column can ever contain values like `GLOBALS`, `pid`, `choice`, `form_folder`, etc. (via a bug elsewhere, a compromised account with prefs-editing rights, or future injection), this allows overwriting arbitrary script/global variables, potentially altering control flow or the `$GLOBALS` superglobal itself. This revives the register_globals class of vulnerability.
**Severity:** High

### 5. Stored XSS – inconsistent output encoding
**Location:** Multiple places, e.g.:
```php
&nbsp;<?php echo $HPI1; ?>
...
echo $item['codetext']."<br />";
echo $item['code']."<br />";
echo  $item['plan']."</div><br />";
...
foreach ($PLAN_items as $item) { echo $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
```
**OWASP Category:** A03:2021 – Injection (Stored XSS)
**Problem:** Nearly every other field in the report is wrapped in `text()` for output encoding, but `HPI1/HPI2/HPI3`, `PLAN`/`PLAN2`, and the `code`/`codetext`/`plan` fields from `form_eye_mag_impplan` are echoed raw. If any upstream entry form allows free text/HTML in these fields (common for "plan" narrative fields), this becomes stored XSS executed whenever the report is viewed/printed — including by other staff.
**Severity:** High (ePHI context, multi-user exposure)

---

## Medium

### 6. SQL built via string concatenation of session value
**Location:**
```php
if ($_SESSION['pc_facility']) {
  $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
}
```
**OWASP Category:** A03:2021 – Injection (SQL) / Security Misconfiguration
**Problem:** Even though `pc_facility` is a session variable, concatenating it into SQL instead of using a bound parameter is inconsistent with secure coding practice elsewhere in this file and creates risk if this session value is ever set from a less-trusted path.
**Severity:** Medium

### 7. Suppressed-error `extract()` of DB rows into local scope
**Location:**
```php
@extract($objQuery);
...
@extract($encounter_data);
```
**OWASP Category:** A04:2021 – Insecure Design
**Problem:** Extracting full DB rows into the local symbol table can silently overwrite function parameters/control variables (`$pid`, `$encounter`, `$choice`, etc.) if a column name collides. The leading `@` additionally suppresses any diagnostic warning, making such collisions invisible during testing.
**Severity:** Medium

### 8. Weak HTML escaping helper
**Location:**
```php
function report_ACT($term) {
  $term = nl2br(htmlspecialchars($term,ENT_NOQUOTES));
  return $term."&nbsp;";
}
```
**OWASP Category:** A03:2021 – Injection (XSS)
**Problem:** `ENT_NOQUOTES` leaves both single and double quotes un-encoded. While currently used only in text nodes (lower risk), it's an inconsistent/weaker encoding than the project's standard `text()` helper and is risky if reused in an attribute context later.
**Severity:** Medium

### 9. No audit logging of ePHI access
**Location:** Entire file – no call to any logging/audit function (e.g., OpenEMR's event logging) when a patient report is rendered.
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
**Problem:** Viewing a clinical report containing PHI should be logged for HIPAA accountability and incident detection. No such logging exists in this new form.
**Severity:** Medium

---

## Low / Informational

### 10. Reliance on legacy global sanitize flag instead of consistent parameterization
**Location:** `$sanitize_all_escapes=true;` plus mixed use of parameterized and non-parameterized queries.
**OWASP Category:** A05:2021 – Security Misconfiguration
**Problem:** The file mixes modern `sqlStatement($q, $params)` usage with raw string concatenation (see items 3 & 6), relying on a global escaping toggle as a safety net. This is fragile and should be replaced by consistent parameterized queries throughout.
**Severity:** Low

### 11. Potential local file disclosure via PDF rendering path
**Location:**
```php
if ($PDF_OUTPUT) {
  echo "<img src='". $from_file."' style='width:220px;'>";
}
```
**OWASP Category:** A01:2021 – Broken Access Control (combined with item 1) / Information Disclosure
**Problem:** `$from_file` is a server filesystem path built from `$pid`/session site id. Combined with the IDOR in item 1, this could let an unauthorized user cause retrieval/rendering of another patient's locally stored photo/document during PDF generation.
**Severity:** Low (contingent on item 1 being fixed)

### 12. Possible outdated bundled third-party code
**Location:** File header references the "HTML5 Sketch plugin... Copyright (C) 2011 by Michael Bleigh and Intridea, Inc."
**OWASP Category:** A06:2021 – Vulnerable and Outdated Components
**Problem:** Code dated 2011 bundled/vendored into the application should be checked for known vulnerabilities and update/patch status; no version pinning or provenance is indicated.
**Severity:** Low (needs verification against actual included JS, not shown in this diff)

### 13. No CSRF token validation
**Location:** Entire file (GET-parameter driven, read-only rendering).
**OWASP Category:** A01:2021 – Broken Access Control (CSRF) — low relevance here since it's a read-only GET report, but worth noting for consistency with OpenEMR's CSRF framework if this page is ever extended to accept POST/state-changing input.
**Severity:** Low

---

## Summary
The most urgent issues are the **complete absence of patient/encounter-level authorization checks (critical IDOR)**, a **reflected XSS via the `ptid` parameter**, a **SQL injection in `display_draw_image()`**, and the **dangerous `$$LOCATION` dynamic variable assignment** pattern. These should block merge until remediated. The remaining stored-XSS and logging gaps should also be fixed before release given this code renders and prints protected health information.