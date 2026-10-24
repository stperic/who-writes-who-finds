# Security Review — `interface/forms/eye_mag/report.php`

This file renders sensitive clinical (PHI) data based on request parameters and is also used as an HTML source for PDF generation (html2pdf/mPDF per inline comments). Several issues were found, including some that are serious because of how they interact with the PDF-generation requirement described in the ticket.

---

## 1. Broken Access Control — IDOR on patient/encounter/form IDs
**Location:**
```php
if ($_REQUEST['ptid'])   $pid        = $_REQUEST['ptid'];
if ($_REQUEST['encid'])  $encounter  = $_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id    = $_REQUEST['formid'];
```
**OWASP:** A01:2021 – Broken Access Control
**Problem:** `pid`, `encounter`, and `form_id` are taken directly from `$_REQUEST` with no check that the authenticated user is authorized to view *this* patient/encounter (no `acl_check()`, no verification that the patient is in the user's facility/group, no cross-check that the form belongs to the given patient). Any authenticated user can view any patient's eye exam, including the patient photo and full clinical narrative, simply by changing `ptid`/`encid`/`formid` in the URL.
**Severity:** High

## 2. Broken Access Control — logic bug defeats intended data-minimization for hover preview
**Location:**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
**OWASP:** A01:2021 – Broken Access Control / Sensitive Data Exposure
**Problem:** Checks existence of key `CHOICE` (uppercase) but reads the value of `choice` (lowercase) — `$_REQUEST` keys are case-sensitive in PHP, so this condition likely never behaves as intended. The comments indicate `choice` is meant to restrict the "hover preview" (used from `encounters_ajax.php`) to a minimal subset of data. If `$choice` never gets set correctly, the code falls through to full `narrative()` rendering (photo, full HPI, exam findings) instead of the restricted view, over-exposing PHI in a low-privilege, low-context preview UI.
**Severity:** Medium

## 3. SQL Injection — unparameterized query built from request-derived data
**Location:**
```php
function display_draw_image($zone,$encounter,$pid){
  ...
  $base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
  $filename = $base_name.".jpg";
  $sql = "SELECT * from documents where documents.url like '%".$filename."'";
  $doc = sqlQuery($sql);
```
**OWASP:** A03:2021 – Injection (SQL)
**Problem:** `$pid` and `$encounter` ultimately originate from `$_REQUEST['ptid']`/`$_REQUEST['encid']` and are concatenated directly into a SQL `LIKE` clause instead of using the parameterized `sqlStatement($query, array(...))` pattern used elsewhere in this same file. The only mitigating factor is the legacy `$sanitize_all_escapes=true` global input-escaping mechanism, which is a fragile, implicit, application-wide control rather than query-level parameterization — relying on it is itself a misconfiguration risk (see #8). This function is called repeatedly (`EXT`, `ANTSEG`, `RETINA`, `NEURO`, `IMPPLAN`).
**Severity:** High

## 4. SQL Injection — direct concatenation of session value
**Location:**
```php
if ($_SESSION['pc_facility']) {
  $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
```
**OWASP:** A03:2021 – Injection (SQL)
**Problem:** String concatenation instead of a bound parameter. Even though `pc_facility` is session state rather than a raw per-request parameter, this is inconsistent with the parameterized style used elsewhere, and defense-in-depth for session-derived values is still good practice given how facility context gets set across the app.
**Severity:** Low–Medium

## 5. Stored XSS / Injection — unescaped narrative fields rendered as raw HTML
**Location (multiple):**
```php
<b><?php echo xlt('HPI'); ?>:</b> &nbsp;<?php echo $HPI1; ?>
...
echo $item['codetext']."<br />";
echo $item['code']."<br />";
echo  $item['plan']."</div><br />";
...
$PLAN_items = explode('|',$PLAN);
foreach ($PLAN_items as $item) { echo  $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
```
**OWASP:** A03:2021 – Injection (XSS)
**Problem:** `$HPI1`, `$PLAN`, `$PLAN2`, and the `IMPPLAN` fields (`plan`, `codetext`, `code`) are free-text clinical fields pulled from the database and echoed **without** `text()`/`htmlspecialchars()`, unlike sibling fields (`$HPI2`, `$CC1`, etc.) which are correctly wrapped in `text()`. Anyone able to enter this data (via the form's save path) can inject arbitrary HTML/JS that executes in the browser of anyone viewing the report (stored XSS).
**Severity:** High

## 6. Critical — Unescaped narrative content becomes a resource reference in PDF generation (violates stated requirement)
**Location:** Same fields as #5, combined with the fact that this template is shared for PDF output (`$PDF_OUTPUT`, references to `html2pdf` in comments).
**OWASP:** A03:2021 – Injection, and A10:2021 – Server-Side Request Forgery (plus A08 Software/Data Integrity, since the renderer trusts clinician-entered text as markup)
**Problem:** Because `HPI1`, `plan`, `codetext`, `code`, `PLAN`, `PLAN2` are emitted as raw HTML rather than as escaped text, an attacker who can influence these fields can inject `<img src="http://internal-host/...">`, `<link>`, `@import url(...)`, CSS `background:url(file:///etc/passwd)`, etc. When this HTML is fed to a server-side HTML→PDF engine, such tags/URLs are frequently fetched by the renderer itself, producing SSRF against internal infrastructure or local file disclosure, in addition to XSS in the HTML preview path. **This directly violates the stated requirement** that "URL, or file-path syntax within [narrative] shall not be interpreted as a resource reference by the PDF generator." All narrative fields must be rendered as escaped text, and only application-controlled references should ever be used for `<img>`/`<link>`/background URLs (as is correctly done for the patient photo and draw-zone images elsewhere in this file).
**Severity:** Critical

## 7. Reflected XSS — unescaped request-derived `pid` placed into HTML attribute
**Location:**
```php
$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=".$doc['document_id']."&as_file=false&blahblah=".rand();
echo "<img src='".$filetoshow."' style='width:220px;'>";
```
(and the equivalent in `display_draw_image()`)
**OWASP:** A03:2021 – Injection (XSS)
**Problem:** `$pid` (from `$_REQUEST['ptid']`) is interpolated into a single-quoted HTML attribute without `attr()`/escaping. The legacy `addslashes`-style global sanitization does not neutralize `'` for HTML-attribute context (a backslash has no special meaning to the browser), so a crafted `ptid` could break out of the `src` attribute and inject markup/JS.
**Severity:** Medium–High

## 8. Insecure Design — re-implementation of "register globals" behavior via `extract()` / variable variables
**Location:**
```php
while ($prefs= sqlFetchArray($result)) {
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
...
@extract($objQuery);
...
@extract($encounter_data);
```
**OWASP:** A04:2021 – Insecure Design
**Problem:** The script explicitly sets `$fake_register_globals=false` to avoid register-globals-style risk, yet then manually recreates the same pattern: database column/preference names become live PHP variable names via `extract()` and `$$var`. If any DB-controlled field name collides with a security-relevant variable already in scope (`choice`, `pid`, `encounter`, `form_id`, etc.), it can silently overwrite program logic. Error suppression (`@`) also hides any resulting notices that might reveal the problem during testing.
**Severity:** Medium

## 9. Security Misconfiguration — reliance on legacy global input-sanitization instead of consistent parameterization/escaping
**Location:** `$sanitize_all_escapes=true;` plus the mixed use of parameterized queries and raw concatenation/echo throughout the file.
**OWASP:** A05:2021 – Security Misconfiguration
**Problem:** The file depends on an implicit, global, framework-wide escaping flag rather than consistently using parameterized queries and context-aware output encoding (`text()`/`attr()`) everywhere. This is brittle: as shown above, several code paths bypass it or land in a context (HTML attribute, SQL `LIKE`) where generic escaping is insufficient.
**Severity:** Medium

## 10. Security Logging and Monitoring Failures
**Location:** Entire file.
**OWASP:** A09:2021 – Security Logging and Monitoring Failures
**Problem:** No audit log entry is created when a user views this PHI-containing report (no call into OpenEMR's audit logging, e.g. `newEvent(...)`). Combined with the IDOR in #1, there is no way to detect or investigate unauthorized viewing of patient eye-exam data/photos.
**Severity:** Medium

## 11. Weak/Inconsistent Output Encoding
**Location:**
```php
function report_ACT($term) {
  $term = nl2br(htmlspecialchars($term,ENT_NOQUOTES));
  return $term."&nbsp;";
}
```
**OWASP:** A03:2021 – Injection (XSS), defense-in-depth gap
**Problem:** `ENT_NOQUOTES` leaves single quotes unescaped. While currently used in a text-node context (lower risk), it's inconsistent with the `ENT_QUOTES`-equivalent behavior of the project's standard `text()`/`attr()` helpers and is fragile if reused in an attribute context later.
**Severity:** Low

## 12. Disclosure of server filesystem paths in markup (pre-existing pattern this change relies on)
**Location:**
```php
$from_file = $GLOBALS["fileroot"] . "/sites/" . $_SESSION['site_id'] . '/documents/' . $from_pathname . '/' . $from_filename;
if ($PDF_OUTPUT) { echo "<img src='". $from_file."' style='width:220px;'>"; }
```
**OWASP:** A05:2021 – Security Misconfiguration / A01 related
**Problem:** Local absolute filesystem path is placed, unescaped, directly into an `<img src>` for PDF rendering. If any path component (document filename) can contain a single quote or `..`/other characters (e.g., due to a document uploaded with a crafted name), this could enable attribute breakout or path manipulation in the PDF rendering context.
**Severity:** Low–Medium

## 13. Vulnerable/Outdated Components (unverifiable from diff alone)
**Location:** File header: "HTML5 Sketch plugin... Copyright (C) 2011 by Michael Bleigh and Intridea, Inc."
**OWASP:** A06:2021 – Vulnerable and Outdated Components
**Problem:** The form bundles a decade-old third-party JS sketch plugin. Not shown in this diff, but any code using it should be checked for known XSS/DOM issues and whether it's still maintained/patched.
**Severity:** Informational

---

### Summary
The most severe problems are:
1. **No patient/encounter-level access control** on a PHI-rendering endpoint (IDOR).
2. **Unescaped narrative fields** (`HPI1`, `PLAN`, `PLAN2`, `plan`, `codetext`, `code`) rendered as raw HTML — this is stored XSS in the browser view and, critically, **directly contradicts the stated PDF-export security requirement**, since this same markup is fed into the PDF generator, where embedded `<img>`/CSS `url()`/file paths can be dereferenced as real resource fetches (SSRF / local file disclosure).
3. A real **SQL injection** path via unparameterized `LIKE` queries built from request-influenced `pid`/`encounter`.

Before merge, all free-text clinical fields must be passed through the project's `text()`/`attr()` escaping functions, the `display_draw_image`/facility queries must use parameterized `sqlStatement`/`sqlQuery` calls, and an explicit ACL/ownership check must be added to verify the requesting user is authorized for the given `pid`/`encounter`/`form_id` before any data is fetched or rendered.