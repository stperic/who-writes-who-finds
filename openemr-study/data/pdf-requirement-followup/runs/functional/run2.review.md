# Security Review: `interface/forms/eye_mag/report.php`

## Critical / High Severity

### 1. Broken Access Control — No patient/encounter authorization check (IDOR)
**Location:** Top of file —
```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
```
and throughout `narrative()`, `eye_mag_report()`, `display_draw_image()`.

**Problem:** `$pid`, `$encounter`, and `$form_id` are taken directly from the request and used to pull clinical narrative, exam drawings, patient photographs and provider signatures, with **no call to `acl_check()`**, no verification that the current user is assigned to this patient/encounter, and no check that the encounter actually belongs to the supplied patient. Any authenticated user (regardless of role/facility) can change `ptid`/`encid`/`formid` in the URL and view another patient's full eye exam, including the patient photo and physician signature image. This is a textbook IDOR against PHI.

**Severity:** Critical (PHI disclosure, HIPAA-relevant).

---

### 2. Stored XSS — unescaped clinical free-text echoed to page
**Location:**
```php
<b><?php echo xlt('HPI'); ?>:</b>   
&nbsp;<?php echo $HPI1; ?>
```
and later:
```php
echo $PLAN_items ... echo $item."<br />";
if ($PLAN2) { echo $PLAN2."<br />"; }
...
echo $item['codetext']."<br />";
echo $item['code']."<br />";
echo $item['plan']."</div><br />";
```

**Problem:** Unlike almost every other field in this file (which is correctly wrapped in `text()`), `$HPI1`, `$PLAN`, `$PLAN2`, and the `IMPPLAN` fields (`codetext`, `code`, `plan`) are echoed **without `text()`/`htmlspecialchars()`**. These are free-text clinical fields entered by staff and stored in the DB; if they contain `<script>` or event-handler payloads, the payload executes in the browser of whoever views the report (including the "mouse-over" encounter history view used by other clinicians, and in PDF rendering engines that execute HTML/JS). This is a classic stored XSS that can lead to session hijacking of clinical staff.

**Severity:** High.

---

### 3. SQL Injection — string concatenation instead of parameterized query
**Location (`narrative()`):**
```php
if ($_SESSION['pc_facility']) {
    $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
} else {
    $sql = "SELECT * FROM facility ORDER BY billing_location DESC LIMIT 1";
}
$facility = sqlQuery($sql);
```
**Location (`display_draw_image()`):**
```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```

**Problem:** The rest of the file correctly uses `sqlStatement($query, array(...))` with `?` placeholders, but these two spots build raw SQL by string concatenation. `$pid`/`$encounter` originate from `$_REQUEST['ptid']`/`$_REQUEST['encid']` and are never cast to integers before being embedded in a query. The file only relies on the legacy `$sanitize_all_escapes = true` global-escaping mechanism rather than true parameterization — a fragile, bypass-prone pattern that is inconsistent with the rest of the code and should be fixed to use bound parameters.

**Severity:** High (request-controlled values reach SQL without prepared-statement binding).

---

## Medium Severity

### 4. Insecure Design — dynamic variable creation from DB-stored data (`extract()` / variable-variables)
**Location:**
```php
while ($prefs= sqlFetchArray($result))   {    
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
...
@extract($objQuery);
...
@extract($encounter_data);
```
**Problem:** Using `extract()` on query results and `$$LOCATION` to dynamically create globals based on a DB column (`LOCATION`) re-introduces register-globals-style risk. If the `form_eye_mag_prefs.LOCATION` value could ever be influenced by user input (now or via future code changes), an attacker could create/overwrite security-relevant variables (`$choice`, `$pid`, `$form_folder`, etc.) used later in the same request, leading to logic bypass. Even without that specific vector, this pattern is fragile and makes the code's data flow impossible to reason about securely.

**Severity:** Medium.

### 5. Security Misconfiguration — error suppression hides failures
**Location:** `@extract($objQuery);`, `@extract($encounter_data);`
**Problem:** Blanket `@` suppression hides malformed query results, missing records, or type errors that could indicate tampering or injection attempts, and makes debugging/monitoring harder.
**Severity:** Low–Medium.

### 6. Security Logging & Monitoring Failure — no audit trail for PHI access
**Location:** Entire file.
**Problem:** The report renders patient narrative, images, and photographs but never records an audit log entry (OpenEMR normally logs PHI views). Combined with issue #1, unauthorized access to another patient's record would go completely unlogged.
**Severity:** Medium.

### 7. Minor logic bug with security-relevant naming (not itself exploitable but worth flagging)
**Location:**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
**Problem:** Checks the uppercase key but reads the lowercase key; likely a typo. Not a vulnerability per se, but indicates the `$choice`-driven branching (which controls what clinical data is rendered, e.g. `'TEXT'` vs `'DRAW'` vs full narrative) is not well tested — worth fixing before relying on it for any access-limiting logic.
**Severity:** Informational/Low.

---

## Low Severity / Informational

### 8. Local filesystem paths echoed directly into HTML (`$PDF_OUTPUT` branches)
**Location:**
```php
echo "<img src='". $from_file."' style='width:220px;'>";
```
and similarly in `display_draw_image()`.
**Problem:** Server filesystem paths are embedded directly as `img src`. This only matters for the internal PDF renderer, but it does leak internal path structure if output ever reaches the browser directly, and reinforces the need for the access-control fix in #1 since these paths are built from unauthenticated-for-this-patient `$pid`/`$encounter`.
**Severity:** Low.

### 9. Third-party code attribution without version/CVE tracking
**Location:** File header mentions a bundled 2011 "HTML5 Sketch plugin" (Michael Bleigh/Intridea).
**Problem:** The plugin code itself isn't in this diff, but if it is an old bundled dependency with no update path, it should be tracked for known vulnerabilities (Vulnerable and Outdated Components). Not assessable from this diff alone — flagged for follow-up.
**Severity:** Informational.

---

## Summary

The most serious problems are:
1. **No per-patient/encounter authorization check** — any logged-in user can view arbitrary patients' eye exam data, photos, and signatures by manipulating `ptid`/`encid`/`formid` (Broken Access Control, Critical).
2. **Stored XSS** via unescaped `$HPI1`, `$PLAN`, `$PLAN2`, and IMPPLAN fields (Injection/XSS, High).
3. **SQL built via string concatenation** in two places instead of using the parameterized pattern used elsewhere (Injection, High).

These should block merge until access control is added (e.g., `acl_check()` plus verification that the encounter/form belong to a patient the user is authorized for) and all user-sourced/DB-stored text is passed through `text()` before output. The two raw SQL concatenations should be converted to parameterized queries for consistency and safety.