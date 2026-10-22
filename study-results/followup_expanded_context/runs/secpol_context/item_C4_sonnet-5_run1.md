# Security Review: `interface/forms/eye_mag/report.php`

## Critical Findings

### 1. Broken Access Control — No authorization/ownership check on `pid`
**Location:** Top-level script body, `eye_mag_report()`, `narrative()`
**OWASP:** A01:2021 – Broken Access Control
**Problem:** `$pid`, `$encid`/`encounter`, and `$formid` are taken directly from `$_REQUEST` with no call to `acl_check()`, no verification that the current session user/provider is authorized to view this patient, and no verification that the `form_id`/`encounter` actually belongs to the requesting user's facility/patient panel. Any authenticated user (or anyone who can reach this endpoint) can supply arbitrary `ptid`/`encid`/`formid` values and pull another patient's eye exam, photo, impression/plan, physician signature image, etc. This is an IDOR (Insecure Direct Object Reference).
**Severity:** High

### 2. Broken Access Control — Direct file/document disclosure via `controller.php` and local paths
**Location:** `narrative()` patient-photo block, `display_draw_image()`
**OWASP:** A01:2021
**Problem:** Document IDs are derived from SQL lookups keyed by attacker-controlled `$pid`/`$encounter`; the code then either echoes an `<img>` pointing at `controller.php?document&retrieve&patient_id=$pid&document_id=...` or, when `$PDF_OUTPUT` is set, echoes a raw local filesystem path (`$from_file`) directly as an `<img src=...>` without any access check performed inside this script. Combined with #1, this allows retrieval of another patient's protected health information (images).
**Severity:** High

### 3. SQL Injection — raw string concatenation of filenames/IDs into SQL
**Location:**
```php
$sql = "SELECT * from documents where url='file://".$file_location."'";
...
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```
in the commented-out `DRAW` block and in `display_draw_image()`.
**OWASP:** A03:2021 – Injection
**Problem:** `$file_location`/`$filename` are built from `$pid` and `$encounter`, which originate from `$_REQUEST['ptid']`/`$_REQUEST['encid']` without any validation that they are numeric. These values are concatenated directly into a SQL string instead of using parameterized queries (which this file uses correctly elsewhere, e.g. `sqlStatement($query,array(...))`). This is a direct SQL injection vector. Even though the `DRAW`-image-table lookup block is commented out, `display_draw_image()` (which is **live** code, called repeatedly for EXT/ANTSEG/NEURO/RETINA/IMPPLAN) has the exact same unparameterized-concatenation pattern and is actively exploitable.
**Severity:** High

### 4. SQL Injection — unvalidated `$_SESSION['pc_facility']` concatenated into SQL
**Location:**
```php
if ($_SESSION['pc_facility']) {
  $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
}
```
**OWASP:** A03:2021 – Injection
**Problem:** Although session-derived, if `pc_facility` can be influenced by any prior less-trusted code path (or set via a different vulnerable endpoint) this is unparameterized. Should use `sqlQuery` with bound parameters as done elsewhere in the file. Lower likelihood but still a code smell / defense-in-depth failure. This same pattern pre-exists in `custom_report.php` (included context), so it's a repeated anti-pattern across the codebase.
**Severity:** Low–Medium

### 5. Cross-Site Scripting (XSS) — many fields echoed without `text()`/`attr()` escaping
**Location:** Throughout `narrative()`, e.g.:
```php
&nbsp;<?php echo $HPI1; ?>
...
if ($CC2) { echo "..."; echo "<b>".xlt('Chief Complaint 2'); ?>:</b> &nbsp;<?php echo text($CC2); ?>
...
echo $item['codetext']."<br />";
...
echo $item['plan']."</div><br />";
...
echo $CHRONIC2... (unescaped)
echo $PLAN_items (exploded, printed raw)
echo $PLAN2 (raw)
```
**OWASP:** A03:2021 – Injection (Stored XSS)
**Problem:** `$HPI1`, `$item['codetext']`, `$item['plan']` (after `str_replace` for newlines only — not HTML-escaped), `$CHRONIC2`, `$CHRONIC3`, `$PLAN` items, and `$PLAN2` are all database-sourced free-text fields that get echoed directly into HTML **without** `text()`/`attr()` sanitization, unlike the majority of fields in the file, which correctly use `text()`. If any upstream form (`new.php`/edit form) allows HTML/script in these fields, this becomes stored XSS rendered in every subsequent view of the encounter report (and in the patient history mouse-over AJAX call path, which is reachable by lower-privileged roles). Note `$sanitize_all_escapes=true;` is set, which provides a legacy magic-quotes-like global escaping layer in OpenEMR, but that does not reliably prevent all HTML injection when values are later echoed raw into HTML context — only `text()`/`attr()` do proper context-aware output encoding.
**Severity:** Medium–High (depends on whether `$sanitize_all_escapes` fully mitigates; should not be relied on as sole XSS defense)

### 6. Insecure Design — Use of `extract()` / dynamic variable variables from DB data
**Location:**
```php
@extract($objQuery);
...
@extract($encounter_data);
...
$LOCATION = $prefs['LOCATION'];
$$LOCATION = text($prefs['GOVALUE']);
...
${"ODSPH_$count_rx"} = $wearing['ODSPH'];
```
**OWASP:** A04:2021 – Insecure Design (also relates to A08 data integrity)
**Problem:** `extract()` on database row data, and dynamic variable creation using DB-controlled key names (`$LOCATION` taken straight from the `form_eye_mag_prefs.LOCATION` column), create variables whose names are attacker/data-influenced. This can lead to variable shadowing/injection of unexpected variables into scope (e.g., overwriting `$pid`, `$choice`, `$PDF_OUTPUT`, or other security-relevant variables used later in the same function), potentially bypassing logic gates like `if ($PDF_OUTPUT)`. This pattern is fragile and error-prone; combined with lack of input validation, it significantly increases the attack surface and is hard to audit. The error-suppression operator `@` additionally hides any issues/warnings that would otherwise surface bugs.
**Severity:** Medium

### 7. Missing Input Validation on all core identifiers
**Location:** Top of file
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```
**OWASP:** A03/A04 – Injection / Insecure Design
**Problem:** No `intval()`/`is_numeric()` checks on `pid`, `encid`, `formid` before they flow into SQL queries (parameterized, mostly) and into file-path construction (`display_draw_image`, patient photo block) where they are **not** parameterized. `$form_name` is also attacher-settable and used to build a `require_once` path:
```php
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
...
require_once("../../forms/".$form_folder."/php/".$form_folder."_functions.php");
```
Although `$form_folder` is hardcoded to `"eye_mag"` (not reassigned from request) in this version, note that `$form_name` is attacker-controlled and used elsewhere/by called functions; any later code path that builds file paths from `$form_name` instead of `$form_folder` would be vulnerable to Local File Inclusion. This is fragile and should be hardened regardless.
**Severity:** Medium

### 8. Local file path disclosure / potential LFI-adjacent issue via document path construction
**Location:** `display_draw_image()`, photo block in `narrative()`
**OWASP:** A01/A05 – Broken Access Control / Security Misconfiguration
**Problem:** Server filesystem absolute paths (`$GLOBALS["fileroot"]`, `$GLOBALS['OE_SITE_DIR']`) are concatenated using `$pid`/`$encounter`/`$from_filename` (derived from a DB `url` column) and directly embedded into `<img src=...>` when `$PDF_OUTPUT` is true, exposing the server's absolute filesystem layout to anyone who can trigger PDF rendering with a crafted `pid`/`encounter`. If the underlying HTML-to-PDF renderer (html2pdf) resolves local file paths, there is also a risk of reading arbitrary files on disk if path construction can be influenced (needs validation that `$pid`/`$encounter` are strictly numeric — currently not enforced here).
**Severity:** Medium

### 9. Security Logging and Monitoring Failures
**Location:** Entire file
**OWASP:** A09:2021
**Problem:** No audit logging (`newEvent`/`EventAuditLogger` calls used elsewhere in OpenEMR for PHI access) is performed when this report is rendered, despite it displaying detailed PHI (clinical exam data, patient photo, physician signature). Given the IDOR in #1, there's no way to detect/trace unauthorized access attempts.
**Severity:** Medium

### 10. Error Suppression Hides Failures Silently
**Location:** `@extract($objQuery);`, `@extract($encounter_data);`
**OWASP:** A09:2021 (logging/monitoring) / general code quality
**Problem:** Use of `@` suppresses PHP warnings/notices that could reveal broken queries (e.g., `sqlQuery()` returning false due to injection attempts or malformed input), reducing visibility into anomalous behavior and making debugging/intrusion detection harder.
**Severity:** Low

---

## Pre-existing issues in related/relied-upon code (not changed by this PR, but touched)

### 11. `custom_report.php` — SQL built by direct string interpolation of `$pid`
**Location:**
```php
$inclookupres = sqlStatement("select distinct formdir from forms where pid = '$pid' AND deleted=0");
...
$sql="SELECT concat(...) FROM `batchcom` ... WHERE batchcom.patient_id='$pid'";
```
**OWASP:** A03:2021 – Injection
**Problem:** `$pid` is interpolated directly rather than bound as a parameter. If `$pid` is not strictly validated upstream as numeric, this is SQL injection. This file is the orchestrator that calls into `eye_mag_report()`, so the trust assumption that `$pid` is "safe" by the time it reaches `report.php` is not actually guaranteed anywhere in this call chain.
**Severity:** Medium (depends on upstream validation, which was not shown to exist)

### 12. `custom_report.php` — unescaped output of several DB fields
**Location:** e.g. `$irow['title']`, `$irow['comments']`, `$row['immunization_note']`, `$note->get_note()`, `lookup_code_descriptions($dcode)` echoed without `text()`.
**OWASP:** A03:2021 – Injection (Stored XSS)
**Problem:** Same class of issue as finding #5 — raw echo of DB content without output encoding function (`text()`/`attr()`), relying solely on `$sanitize_all_escapes`, which is not a complete substitute for output encoding.
**Severity:** Medium

---

## Summary Table

| # | Location | OWASP Category | Severity |
|---|----------|----------------|----------|
| 1 | request param handling | A01 Broken Access Control (IDOR) | High |
| 2 | photo/document display | A01 Broken Access Control | High |
| 3 | `display_draw_image()` SQL concat | A03 Injection (SQLi) | High |
| 4 | facility SQL concat | A03 Injection (SQLi) | Low-Med |
| 5 | unescaped HPI/plan/chronic fields | A03 Injection (XSS) | Med-High |
| 6 | `extract()` / dynamic vars from DB | A04 Insecure Design | Medium |
| 7 | missing input validation on pid/encid/formid/formname | A03/A04 | Medium |
| 8 | absolute path disclosure in PDF image src | A01/A05 | Medium |
| 9 | no PHI access audit logging | A09 | Medium |
| 10 | `@` error suppression | A09 | Low |
| 11 | custom_report.php SQL concat | A03 Injection | Medium |
| 12 | custom_report.php unescaped output | A03 Injection (XSS) | Medium |

**Recommendation:** Before merge, at minimum (a) add explicit `acl_check()`/ownership verification that the session user may view the given `pid`/`encounter`/`form_id`; (b) cast `pid`/`encounter`/`form_id` to integers immediately after reading from `$_REQUEST`; (c) parameterize the two raw SQL string concatenations in `display_draw_image()`; (d) wrap `$HPI1`, `$item['codetext']`, `$item['plan']`, `$CHRONIC2/3`, `$PLAN`/`$PLAN2` output in `text()` (or an HTML-safe nl2br equivalent) before echoing.