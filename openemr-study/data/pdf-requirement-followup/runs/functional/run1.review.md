# Security Review: `interface/forms/eye_mag/report.php`

This is a large new file, and while it does use parameterized queries in several places (good), there are multiple significant issues. Below are the findings mapped to OWASP Top 10 (2021).

---

### 1. Broken Access Control — No authorization / ownership check on patient data (IDOR)
**Location:** Top of file:
```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
```
and every downstream use of `$pid`/`$encounter`/`$form_id` in `eye_mag_report()`, `narrative()`, and `display_draw_image()`.

**Problem:** `acl.inc` is `require_once`'d but `acl_check()` (or any patient-access/ACL validation) is never called. There is no verification that the logged-in user is authorized to view the specified `pid`/`encounter`. Any authenticated user (or anyone who can reach this script) can supply an arbitrary `ptid`/`encid`/`formid` and retrieve another patient's full clinical narrative, impression/plan, drawings, and **patient photograph**. This is a classic IDOR / horizontal privilege escalation exposing PHI.

**Severity:** Critical (PHI disclosure, likely HIPAA-reportable).

---

### 2. Injection (SQL) — Unparameterized query built from request-derived data
**Location:** `display_draw_image()`:
```php
$filename = $base_name.".jpg"; // built from $pid, $encounter
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
`$pid` and `$encounter` originate directly from `$_REQUEST['ptid']` / `$_REQUEST['encid']` with no casting/validation, and are concatenated straight into SQL instead of using the parameterized `sqlQuery($sql, $params)` pattern used elsewhere in the same file.

**Severity:** High.

---

### 3. Injection (SQL) — Unparameterized query using session value
**Location:**
```php
if ($_SESSION['pc_facility']) {
  $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
}
```
**Problem:** Inconsistent with the parameterized style used elsewhere; `$_SESSION['pc_facility']` should still be bound via a placeholder rather than concatenated, as a defense-in-depth measure (session state can sometimes be influenced via other bugs, fixation, or shared code paths).

**Severity:** Low/Medium.

---

### 4. Injection (Stored XSS) — Unescaped clinical data echoed to HTML
**Location(s):**
```php
&nbsp;<?php echo $HPI1; ?>                       // missing text()
...
echo $item['codetext']."<br />";                 // IMPPLAN loop
echo $item['code']."<br />";
echo  $item['plan']."</div><br />";
...
$PLAN_items = explode('|',$PLAN);
foreach ($PLAN_items as $item) { echo  $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
```
**Problem:** Every other field in this file is correctly wrapped with `text()`/`xlt()`/`attr()`, but `HPI1`, the IMPPLAN `codetext`/`code`/`plan` fields, and the `PLAN`/`PLAN2` free-text fields are echoed raw. These are user-entered clinical text fields pulled straight from the database, so this is a stored XSS vector — malicious script stored once can execute in the browser of every clinician/staff member who later views the report (including higher-privileged users), enabling session hijacking, data exfiltration, etc.

**Severity:** High.

---

### 5. Injection (Reflected XSS) — Unescaped request-derived value in HTML attribute
**Location:**
```php
$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=".$doc['document_id']."&as_file=false&blahblah=".rand();
echo "<img src='".$filetoshow."' style='width:220px;'>";
```
and similarly in `display_draw_image()`.

**Problem:** `$pid` comes directly from `$_REQUEST['ptid']` and is embedded into an `<img src="...">` attribute without `attr()`/`htmlspecialchars()` escaping. A crafted `ptid` value containing a quote/angle bracket can break out of the attribute and inject markup/script.

**Severity:** Medium-High.

---

### 6. Insecure Design / Security Misconfiguration — Use of `extract()` on DB result rows
**Location:**
```php
@extract($objQuery);
...
@extract($encounter_data);
```
**Problem:** Extracting an entire DB row into local variable scope recreates a `register_globals`-style risk despite the file explicitly setting `$fake_register_globals=false;`. If any DB column name collides with a sensitive control variable used later in the script (`$choice`, `$PDF_OUTPUT`, `$cols`, etc.), stored data could silently alter program logic/output. Error suppression (`@`) also hides any resulting notices that would reveal the problem.

**Severity:** Medium.

---

### 7. Insecure Design — Dynamic variable creation from stored preference data
**Location:**
```php
while ($prefs= sqlFetchArray($result))   {    
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
```
**Problem:** Variable variables (`$$LOCATION`) whose *name* is taken from a database column create the same class of risk as above — if the `LOCATION` value could ever be influenced by an attacker (e.g., via a separate flaw in the preferences-saving code, not shown here), arbitrary variable names could be set in this scope.

**Severity:** Medium.

---

### 8. Broken Access Control / Path Disclosure — Cross-patient document/image retrieval
**Location:** `narrative()` (patient photo block) and `display_draw_image()`.

**Problem:** Because `$pid`/`$encounter` are unauthenticated-for-ownership (see #1), the document lookup and local filesystem path construction (`$GLOBALS["fileroot"]."/sites/".$_SESSION['site_id']."/documents/".…`) effectively allow retrieval of another patient's photograph and drawing images by simply changing `ptid`/`encid` in the request. Combined with #1, this is a concrete exploit path for PHI disclosure, not just a theoretical IDOR.

**Severity:** High (PHI exposure).

---

### 9. Security Logging and Monitoring Failures — No audit trail for PHI access
**Location:** Entire file / `narrative()`.

**Problem:** The report displays full clinical narrative, impression/plan, drawings and patient photograph, yet there is no call to OpenEMR's audit/event logging (e.g., `newEvent()`), unlike many other PHI-access flows in OpenEMR. There is no record of who viewed which patient's report, hampering breach detection/forensics.

**Severity:** Medium.

---

### 10. Dead code retaining a SQL injection pattern (hygiene / future risk)
**Location:** Commented-out block inside `eye_mag_report()`:
```php
// $sql = "SELECT * from documents where url='file://".$file_location."'";
```
**Problem:** Not currently executable, but it is built from unsanitized `$pid`/`$encounter`/`$zone`. If ever uncommented/reused (as the comments suggest it might be a template for other code), it reintroduces SQL injection. Should be removed rather than left commented.

**Severity:** Low (currently inert, but a latent risk / bad example to leave in the codebase).

---

### 11. Weak input validation of identifiers
**Location:** `$pid`, `$encounter`, `$form_id` assignments at top of file.

**Problem:** None of these identifiers are validated as integers (`is_numeric`/`(int)` cast) before being used in SQL, file-path construction, and URL generation. This is a root cause contributing to findings #1, #2, #5, and #8. Relying solely on `$sanitize_all_escapes` (which performs `addslashes`-style escaping) is not a substitute for strict type validation or parameterized queries/output encoding.

**Severity:** Medium (amplifies other findings).

---

## Summary

The most serious problems are:
1. **No authorization check tying `pid`/`encounter` to the current user's permitted patients** — allows any user to pull another patient's full eye exam report, images, and photo (Broken Access Control / PHI leak).
2. **SQL injection** in `display_draw_image()` via unparameterized, request-derived query.
3. **Stored XSS** via several unescaped clinical text fields (`HPI1`, IMPPLAN `code`/`codetext`/`plan`, `PLAN`/`PLAN2`).
4. **Reflected XSS** via unescaped `$pid` placed into an `<img src>` attribute.
5. Risky `extract()`/variable-variable patterns that could allow stored data to influence script control flow.
6. No audit logging of PHI access.

These should be fixed before merge: add explicit ACL/ownership checks for `pid`/`encounter`/`form_id`, parameterize all SQL (including the `documents` LIKE query and facility query), consistently wrap all DB-sourced output with `text()`/`attr()`, remove/replace the `extract()`/`$$var` patterns with explicit field assignment, cast identifiers to integers, and add audit-event logging for report views.