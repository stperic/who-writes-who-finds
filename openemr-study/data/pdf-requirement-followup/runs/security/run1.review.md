# Security Review: `interface/forms/eye_mag/report.php`

## Summary
This file has several serious issues: broken access control (IDOR) on PHI, SQL injection, multiple stored‑XSS sinks, and an unescaped‑narrative path that directly violates the stated PDF‑export security requirement (narrative content can be interpreted as HTML/CSS/URL/file resource references by the PDF renderer, creating an SSRF/local‑file‑read vector). Details below.

---

### 1. Broken Access Control / IDOR on patient data
**Location:** top of file —
```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
```
**Category:** A01:2021 – Broken Access Control
**Problem:** `$pid`, `$encounter`, and `$form_id` are taken directly from the request with no validation (not even `is_numeric`) and no check that the authenticated user is authorized to view this patient/encounter (no `acl_check`, no verification against the session's active patient or care-team). The SQL joins only confirm internal referential consistency between `pid`/`encounter`/`form_id`, not that the *requesting user* may see them. Any authenticated user can enumerate `ptid`/`encid` to view another patient's eye exam, chief complaint/HPI narrative, impression/plan, and patient photo.
**Severity:** Critical (PHI exposure, HIPAA-relevant).

---

### 2. SQL Injection via unvalidated `$pid`/`$encounter` concatenation
**Location:** `display_draw_image()`
```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
**Category:** A03:2021 – Injection (SQL Injection)
**Problem:** `$pid` and `$encounter` originate from `$_REQUEST['ptid']`/`$_REQUEST['encid']` and are concatenated directly into a raw SQL string instead of using the parameterized style (`?` placeholders) used everywhere else in this file. An attacker can inject SQL through these parameters (e.g., `ptid=x' UNION SELECT ...-- `). Note also that this query has **no `pid` filter at all**, so even without injection it allows retrieving any patient's stored clinical images by guessing/controlling the filename pattern — compounding the IDOR above.
**Severity:** Critical.

---

### 3. SQL Injection via session value concatenation
**Location:** `narrative()`
```php
if ($_SESSION['pc_facility']) {
  $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
}
```
**Category:** A03:2021 – Injection (SQL Injection)
**Problem:** Even though this is a session variable rather than direct request input, it is concatenated unparameterized while every other query in the file correctly uses placeholders. Depending on how `pc_facility` is populated elsewhere, this is an inconsistent and risky pattern that should use `sqlQuery($sql, array($_SESSION['pc_facility']))`.
**Severity:** Medium.

---

### 4. Stored XSS — multiple unescaped outputs of DB/user-entered narrative
**Locations:**
```php
&nbsp;<?php echo $HPI1; ?>                                    // missing text()
if ($CHRONIC2) echo "&nbsp;".$CHRONIC2."<br />";
if ($CHRONIC3) echo "&nbsp;".$CHRONIC3."<br />";
...
echo $item['codetext']."<br />";
echo $item['code']."<br />";
echo  $item['plan']."</div><br />";
...
foreach ($PLAN_items as $item) { echo  $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
```
**Category:** A03:2021 – Injection (Cross-Site Scripting)
**Problem:** Nearly every other field in this file is correctly wrapped in `text()` before output, but these specific fields (HPI1, CHRONIC2/3, IMPPLAN code/codetext/plan, PLAN/PLAN2 items) are echoed raw. These come from database columns populated by prior user input (free-text clinical narrative, impression/plan entries). Any HTML/JS stored in these fields will execute in the browser when the report is viewed — classic stored XSS, especially dangerous in a multi-role clinical system where lower-privileged staff may enter this text and higher-privileged users view it.
**Severity:** High.

---

### 5. Unescaped narrative treated as HTML in PDF rendering path → SSRF / local file disclosure risk
**Location:** Same sinks as #4, combined with the `$PDF_OUTPUT` branches and the commented reference to the `html2pdf` renderer.
**Category:** A10:2021 – Server-Side Request Forgery (and A08 Software/Data Integrity Failures — template/content injection)
**Problem:** This directly violates the stated requirement: *"User-controlled narrative shall be rendered as content... shall not be interpreted as a resource reference by the PDF generator."* Because fields like `$HPI1`, `$item['plan']`, `$item['codetext']`, and `$PLAN` items are emitted as raw, unescaped HTML into markup that is fed to an HTML-to-PDF converter, an attacker (or compromised low-privilege account) can embed `<img src="http://internal-host/...">`, `<link href="...">`, CSS `url(...)`, or `file://` references inside clinical narrative text. Many HTML-to-PDF engines (including html2pdf/wkhtmltopdf-class tools) will fetch such resources server-side during PDF generation, enabling SSRF against internal services or local file disclosure embedded into the generated PDF. The lack of consistent escaping (per #4) means this is not merely theoretical — it's an active injection point feeding the renderer.
**Severity:** Critical (directly contradicts the specified security requirement).

---

### 6. Use of `extract()` on query results
**Location:**
```php
@extract($objQuery);
...
@extract($encounter_data);
```
**Category:** A04:2021 – Insecure Design (CWE-915: Improperly Controlled Modification of Dynamically-Determined Object Attributes)
**Problem:** `extract()` dynamically creates variables named after DB columns, which can silently clobber existing variables such as `$pid`, `$encounter`, `$choice`, `$cols`, etc., if the joined tables (`form_encounter.*`, `form_eye_mag.*`) contain columns with those names. This is fragile and could lead to unexpected control-flow or data leakage as the schema evolves. Error suppression (`@`) also hides any related warnings.
**Severity:** Medium.

---

### 7. Missing audit/access logging for PHI view
**Location:** Entire file — no call to OpenEMR's audit logging (`newEvent`/equivalent) when rendering patient clinical data or photos.
**Category:** A09:2021 – Security Logging and Monitoring Failures
**Problem:** Viewing a patient's eye exam report (including narrative, impression/plan, and photo) is a PHI access event. No logging call is present to record who viewed which patient's record, hindering detection of the IDOR described in #1/#2.
**Severity:** Medium.

---

### 8. Weak quoting in `report_ACT()`
**Location:**
```php
function report_ACT($term) {
  $term = nl2br(htmlspecialchars($term,ENT_NOQUOTES));
  return $term."&nbsp;";
}
```
**Category:** A03:2021 – Injection (XSS, defense-in-depth gap)
**Problem:** `ENT_NOQUOTES` leaves single/double quotes unescaped. Current usages are in text nodes, so impact today is limited, but this is a latent risk if the helper is reused in an attribute context, and it is inconsistent with the `text()` helper used elsewhere in the codebase which should be preferred.
**Severity:** Low.

---

### 9. Dead code with SQL/path injection pattern (latent risk)
**Location:** Commented-out block inside `if ($choice == 'DRAW')`:
```php
$file_location = ... $pid ... $encounter ...;
$sql = "SELECT * from documents where url='file://".$file_location."'";
```
**Category:** A03:2021 – Injection (latent)
**Problem:** Currently inert (inside a `/* ... */` comment), but it builds a SQL query and file path directly from `$pid`/`$encounter`/`$side`/`$zone` without parameterization. If ever re-enabled, it reproduces the same SQLi/path-traversal issues as #2.
**Severity:** Informational (flag for removal rather than re-enabling).

---

### 10. Miscellaneous input-handling hygiene
**Location:**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
**Category:** A04:2021 – Insecure Design (code quality / inconsistency)
**Problem:** Checks the uppercase key but reads the lowercase one — functionally this makes `$choice` effectively unsettable via this line (likely a bug), illustrating inconsistent, unvalidated handling of request input throughout the file. Not independently exploitable, but indicative of the general lack of input validation that underlies issues #1–#2.
**Severity:** Low.

---

### 11. Vulnerable/outdated dependency (cannot fully confirm from diff)
**Location:** References to `html2pdf` in comments, used for `$PDF_OUTPUT` rendering.
**Category:** A06:2021 – Vulnerable and Outdated Components
**Problem:** If the bundled/required `html2pdf` (or equivalent) library is an old version, it may have known XSS/SSRF/resource-fetch issues that compound finding #5. Recommend confirming the library version and its handling of remote resource/`file://` URIs, and sandboxing/disabling remote fetches in the PDF renderer configuration.
**Severity:** Medium (pending version confirmation).

---

## Recommendations
1. Add explicit authorization checks (ACL + patient/encounter ownership validation against the session) before querying or rendering any data — fixes #1.
2. Parameterize *all* SQL, including the `display_draw_image()` document lookup and the facility lookup, and re-add a `pid`/`encounter` filter to the document query — fixes #2, #3.
3. Wrap every DB-sourced narrative field in `text()` (or equivalent context-aware encoding) before output — fixes #4.
4. For PDF generation specifically, sanitize/strip narrative content of any tags/attributes capable of triggering external resource loads (`img`, `link`, `style`/`url()`, `iframe`, `object`, `file://`), or render narrative as plain text with explicit, app-controlled image placeholders only — required to satisfy the stated PDF export security requirement and fixes #5.
5. Avoid `extract()`; explicitly map only the needed DB columns to local variables.
6. Add audit logging for PHI views.
7. Confirm and, if necessary, update/harden the PDF rendering library configuration to disallow remote resource fetching.