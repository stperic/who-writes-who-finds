# Security Review – `interface/forms/eye_mag/report.php`

## Critical / High Severity

### 1. Broken Access Control – No patient/encounter authorization check (IDOR)
**Location:** Top-level script body, lines handling `$_REQUEST['ptid']`, `$_REQUEST['encid']`, `$_REQUEST['formid']`, and the `eye_mag_report()` / `narrative()` functions that use them.

```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
```

**Problem:** `acl.inc` is `require_once`'d but **no `acl_check()` (or equivalent patient/encounter authorization) call is ever made**. Any authenticated user can supply an arbitrary `ptid`/`encid`/`formid` and retrieve a full clinical eye exam report — chief complaints, HPI, exam findings, impression/plan, patient photo, provider signature — for **any patient in the system**, not just patients they are authorized to see. This is a textbook IDOR exposing PHI.

**Severity:** **Critical** (HIPAA‑relevant PHI disclosure).

---

### 2. SQL Injection + IDOR in `display_draw_image()`
**Location:**
```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
**Problem:** `$pid` and `$encounter` originate from `$_REQUEST` and are concatenated directly into a SQL string instead of using the parameterized `sqlQuery($sql, $params)` pattern used everywhere else in this file. This both (a) permits classic SQL injection (breaking out of the `LIKE` pattern, e.g. via `%` or `'`), and (b) combined with issue #1, allows an attacker to pull image/document records belonging to other patients. Same pattern also appears in the file-lookup query inside the large commented-out `DRAW`/legacy block (`$sql = "SELECT * from documents where url='file://".$file_location."'"`) — dead code today, but a latent injection if ever re-enabled.

**Severity:** **High**.

---

### 3. Stored XSS – unescaped clinical text fields
**Location:** Multiple places in `narrative()`:

```php
<b><?php echo xlt('HPI'); ?>:</b>  &nbsp;<?php echo $HPI1; ?>   // not wrapped in text()
...
echo $item['codetext']."<br />";      // IMPPLAN codetext
echo $item['code']."<br />";          // IMPPLAN code
echo  $item['plan']."</div><br />";   // IMPPLAN plan text
...
$PLAN_items = explode('|',$PLAN);
foreach ($PLAN_items as $item) { echo  $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
...
echo "<img ...><hr ... />".$providerNAME."<br />...";   // PDF branch, no text()
```

**Problem:** Almost every other field in this report correctly uses `text()`/`xlt()`/`attr()` for output encoding, but `HPI1`, the Impression/Plan (`code`, `codetext`, `plan`), the `PLAN`/`PLAN2` free-text order fields, and `providerNAME` (in the PDF signature block) are echoed **raw**. These fields are clinician-entered free text, stored in the database, and rendered to every subsequent viewer of the encounter (including the HTML→PDF pipeline). This is a classic stored XSS vector that can lead to session hijacking, privilege escalation, or malicious PDF content.

**Severity:** **High** (stored XSS in a widely-viewed, PHI-bearing report).

---

## Medium Severity

### 4. SQL Injection via session variable concatenation
**Location:**
```php
if ($_SESSION['pc_facility']) {
    $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
} else {
    $sql = "SELECT * FROM facility ORDER BY billing_location DESC LIMIT 1";
}
```
**Problem:** Inconsistent with the parameterized-query style used elsewhere; `$_SESSION['pc_facility']` is treated as implicitly trusted, but session values can be influenced indirectly in OpenEMR via other endpoints. Should use `sqlQuery($sql, array($_SESSION['pc_facility']))`.

**Severity:** Medium.

### 5. Dangerous use of `extract()` on database result rows
**Location:**
```php
$objQuery = sqlQuery($query, array($encounter, $pid));
@extract($objQuery);
...
$encounter_data = sqlQuery($query, array($encounter, $pid));
@extract($encounter_data);
```
Also widespread use of variable-variables: `$$LOCATION = text($prefs['GOVALUE']);`, `${"ODSPH_$i"} = ...`.

**Problem:** `extract()` imports arbitrary column names as variables into the active scope with no allow-list, and the preferences loop (`$$LOCATION = ...`) does the same keyed off a DB column value. While the values currently come from DB rows rather than direct request input, this pattern is fragile and historically a source of variable-overwrite vulnerabilities (CWE-621) in PHP applications, especially combined with `$sanitize_all_escapes` legacy “magic” global sanitization rather than modern input handling. Errors are also suppressed with `@`, hiding failures that should be logged.

**Severity:** Medium (insecure design / maintainability-driven security risk).

### 6. Information disclosure / IDOR of provider signature images
**Location:**
```php
$providerID  =  getProviderIdOfEncounter($encounter);
...
$from_file = $GLOBALS["webserver_root"] ."/interface/forms/".$form_folder."/images/sign_".$providerID.".jpg";
```
**Problem:** Because `$encounter` is unauthenticated/unauthorized per issue #1, an attacker can enumerate arbitrary encounters to retrieve provider signature images used for authenticating prescriptions/plans — a fairly sensitive artifact (can aid document forgery).

**Severity:** Medium (compounds issue #1).

---

## Low Severity / Observations

### 7. Missing security logging / audit trail for PHI access
**Location:** Entire file.
**Problem:** There is no call to OpenEMR’s audit logging (`newEvent`, etc.) recording that a user viewed this patient’s eye exam report. Given PHI is displayed, lack of access logging is a gap under OWASP A09 and likely under HIPAA audit requirements.
**Severity:** Low–Medium.

### 8. Error suppression (`@`) hides failures
**Location:** `@extract($objQuery);`, `@extract($encounter_data);`
**Problem:** Suppressing errors/warnings prevents detection of malformed queries or unexpected data, reducing observability of anomalies (ties into logging/monitoring failures).
**Severity:** Low.

### 9. Unvalidated/untyped request parameters used in file-path and DB construction
**Location:** `$pid`, `$encounter`, `$form_id`, `$form_name` from `$_REQUEST` are never validated as numeric/expected format before being used in SQL, file paths, and image URLs.
**Problem:** Defense-in-depth failure — even though `$sanitize_all_escapes` provides some legacy escaping, there is no explicit `is_numeric()`/type-casting validation, which is considered best practice before using identifiers in SQL/path construction.
**Severity:** Low.

### 10. Legacy/implicit reliance on `$sanitize_all_escapes`
**Location:** Top of file.
**Problem:** Relying on a global “auto-sanitize” flag rather than explicit parameterized queries/escaping at each use site is a known fragile pattern in OpenEMR’s history and has previously been bypassed. The SQL injection points above (#2, #4) show this protection is not consistently relied upon or sufficient.
**Severity:** Low (contributing factor to #2/#4).

---

## Not Applicable / No Findings
- No cryptographic operations in this file (A02 – N/A).
- No deserialization or auto-update/integrity-sensitive operations (A08 – N/A).
- No outbound HTTP requests driven by user input (A10 SSRF – N/A).
- No authentication logic added/changed here (relies on `globals.php` session handling) — A07 issues are really the access-control gap already covered in #1.
- Cannot assess A06 (vulnerable/outdated components) from this diff alone, beyond noting bundled third-party “HTML5 Sketch” code of unknown current version.

---

## Summary / Priority Fixes
1. **Add explicit ACL/ownership checks** (`acl_check()` plus verification that `$pid`/`$encounter` belong to a patient/encounter the current user is authorized to view) before any data is queried or rendered. This is the most urgent fix.
2. **Convert all raw SQL string concatenation to parameterized queries** (`display_draw_image()`, facility lookup, and the commented-out DRAW block if ever reactivated).
3. **Wrap all remaining raw `echo` of DB-sourced text** (`$HPI1`, IMPPLAN `code`/`codetext`/`plan`, `$PLAN`/`$PLAN2`, `$providerNAME` in PDF branch) with `text()` (or an HTML-safe renderer that still allows the intentional `<br/>` conversion, e.g., escape first then substitute line breaks).
4. Replace `extract()`/variable-variable patterns with explicit array access for maintainability and to reduce the risk surface.
5. Add audit logging of PHI report views.