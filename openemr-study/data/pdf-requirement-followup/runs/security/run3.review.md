# Security Review — `interface/forms/eye_mag/report.php`

This file has several serious issues. I'll group them by OWASP category.

---

## 1. Broken Access Control (A01:2021) — **Critical**

**Location:**
```php
if ($_REQUEST['ptid'])    $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid'])   $encounter = $_REQUEST['encid'];
if ($_REQUEST['formid'])  $form_id = $_REQUEST['formid'];
```

**Problem:** `$pid`, `$encounter`, and `$form_id` are taken verbatim from the request with no call to `acl_check()`, no verification that the logged-in user is authorized to view *this* patient, and no verification that the user even has an active patient context matching `$pid`. The SQL joins only enforce that the `encounter` row belongs to the `pid` row — they do **not** enforce that the current user is allowed to see that patient.

This means any authenticated user (clinical or non-clinical role) can view **any patient's** eye exam narrative, HPI, impression/plan, refraction data, and patient photograph simply by changing `ptid`/`encid` in the URL — a textbook IDOR. This is PHI exposure and a HIPAA concern.

**Severity:** Critical

---

## 2. Injection — SQL Injection (A03:2021) — **High**

**Location (commented-out but still present / display_draw_image):**
```php
$sql = "SELECT * from documents where url='file://".$file_location."'";
...
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```
`$file_location`/`$filename` are built directly from `$pid` and `$encounter`, which originate from `$_REQUEST`, and are concatenated into the query string instead of using the parameterized `sqlQuery($query, array(...))` pattern used elsewhere in this same file.

**Location:**
```php
$sql = "select * from facility where id=" . $_SESSION['pc_facility'];
```
Same pattern — string concatenation instead of a placeholder.

**Problem:** These bypass the parameterized-query discipline used everywhere else in the file. The only mitigation is the legacy `$sanitize_all_escapes = true` global escaping mechanism, which is a fragile, deprecated substitute for prepared statements (effectively a magic-quotes equivalent) and should not be relied upon as the sole defense.

**Severity:** High (documents query, attacker-controlled input) / Low-Medium (facility query, session-controlled)

---

## 3. Injection — Stored XSS (A03:2021) — **High**

**Location:**
```php
<b>HPI:</b> &nbsp;<?php echo $HPI1; ?>
```
Unlike `$HPI2`/`$HPI3` a few lines later (which correctly use `text()`), `$HPI1` is echoed **raw**, with no `text()`/`htmlspecialchars()`. This value comes straight from the `form_eye_mag` table (`@extract($encounter_data)`), i.e., prior clinical free-text input.

**Location (Impression/Plan rendering):**
```php
if ($item['codetext'] > '')  { echo $item['codetext']."<br />"; }
...
echo $item['code']."<br />";
...
echo  $item['plan']."</div><br />";
```
`codetext`, `code`, and `plan` are pulled from `form_eye_mag_impplan` and only `plan` receives a newline→`<br>` substitution; none are HTML-escaped.

**Location (Orders/Next Visit):**
```php
$PLAN_items = explode('|',$PLAN);
foreach ($PLAN_items as $item) { echo  $item."<br />"; }
if ($PLAN2) { echo $PLAN2."<br />"; }
```
`$PLAN`/`$PLAN2` are also unescaped DB fields.

**Problem:** These are free-text clinical fields that a provider (or an attacker who has compromised a provider account, or exploited an unescaped field upstream in the edit form) can populate with `<script>`, `<img onerror=...>`, etc. Since this report is rendered to clinicians in the browser (and also fed into a PDF generator — see below), this is a classic stored XSS with downstream impact (session theft, UI redress, or SSRF via the PDF path described next).

**Severity:** High

---

## 4. Insecure Design — PDF export resource loading violates stated security requirement — **High**

**Location:**
```php
if ($PDF_OUTPUT) {
    echo "<img src='". $from_file."' style='width:220px;height:120px;'>";
}
```
(both in `narrative()` for the patient photo and in `display_draw_image()`), where `$from_file` is a raw filesystem path built from `$GLOBALS['fileroot']`/`$GLOBALS['OE_SITE_DIR']` and the result of the SQL-injectable document lookup described in #2.

**Problem:** This directly conflicts with the proposed requirement that "URL, or file-path syntax ... shall not be interpreted as a resource reference by the PDF generator" and that the generator "may load images ... only through application-controlled references to authorized clinical media." Here:
- The resolved file path is not validated to belong to the authorized patient/encounter beyond a `LIKE` match that is itself injectable.
- The raw filesystem path (not a mediated, ACL-checked controller endpoint) is handed straight to the HTML-to-PDF renderer as an `<img src>`.
- Combined with the unescaped `$HPI1`/`plan`/`code` fields (#3), attacker-controlled HTML (e.g., `<img src="http://internal-host/...">`, CSS `url(...)`/`@import`) could be injected into the narrative that the PDF engine will render, causing it to fetch attacker-chosen URLs — i.e., **SSRF via the PDF generation pipeline** — or disclose local files if the renderer resolves arbitrary filesystem paths.

**Severity:** High (directly actionable path to SSRF/local file disclosure through PDF export, and non-compliant with the stated requirement)

---

## 5. Insecure Design — unsafe dynamic variable patterns (A04:2021) — **Medium**

**Location:**
```php
@extract($objQuery);
@extract($encounter_data);
$$LOCATION = text($prefs['GOVALUE']);
${"ODSPH_$count_rx"} = $wearing['ODSPH'];
```

**Problem:** Despite explicitly disabling `$fake_register_globals`, the code re-implements register-globals-like behavior via `extract()` and variable variables. This silently populates/overwrites the local symbol table (including variables like `$choice`, `$PDF_OUTPUT`, etc., if column names ever collide) based on DB content and loop counters. This is fragile, very hard to audit for safety, and historically a common root cause of PHP injection/logic bugs. The `@` error suppression also hides failures silently.

**Severity:** Medium

---

## 6. Security Logging & Monitoring Failures (A09:2021) — **Medium**

**Problem:** This page renders full clinical detail (HPI, exam findings, refraction, patient photograph) for a given `pid`/`encounter` with no audit log entry being written for the chart access. Given the IDOR issue in #1, there is also no way to detect or investigate unauthorized cross-patient viewing after the fact.

**Severity:** Medium

---

## 7. Security Misconfiguration / Code Quality (Minor)

- `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` — checks the uppercase key but reads the lowercase one; effectively dead logic. Not itself a vulnerability, but suggests the access-control/validation logic around `$choice` was never completed/tested.
- Mixed use of bare `<?` short tags (e.g., `<? }` ) depends on `short_open_tag` ini setting — portability/misconfiguration risk, not a direct vulnerability.
- Reliance on `$sanitize_all_escapes` / `$fake_register_globals` globals as a blanket defense is an outdated security pattern (A05) that should be replaced by consistent parameterized queries and output encoding everywhere, not just in most places.

---

## 8. Vulnerable/Outdated Components (A06:2021) — **Informational**

The file's header credits a bundled "HTML5 Sketch plugin" (2011, jQuery-era) used for the drawing zones. This diff doesn't include its code, but any bundled third-party JS this old should be confirmed to be patched/maintained or replaced, since very old canvas/sketch jQuery plugins have had known XSS/prototype-pollution issues in the broader ecosystem. Flag for follow-up, not confirmed from this diff alone.

---

## 9. Pre-existing / Dependency Concerns (outside this diff but relied upon)

- `controller.php?document&retrieve&patient_id=$pid&document_id=...` — this report trusts that `controller.php` independently enforces that the requesting user may view `document_id` for `patient_id`. Given the IDOR in #1, if `controller.php`'s own authorization also just trusts `patient_id`/`document_id` from the query string without cross-checking against the session/ACL, the combination compounds the exposure. This should be verified, as it's a dependency this new code relies on for its security.
- `Document::get_url_filepath()`/`get_couch_url()` path construction is trusted here without re-validating that the resulting path is confined to the expected documents directory (no canonicalization/containment check visible) — worth confirming no path traversal is possible if `$d->get_url()`/couch metadata were ever attacker-influenced.

---

### Summary

The most severe problems are:
1. **Missing per-patient authorization (IDOR)** — any user can pull any patient's eye exam report via `ptid`/`encid` (Critical).
2. **Stored XSS** via unescaped `$HPI1`, IMPPLAN `code`/`codetext`/`plan`, and `$PLAN`/`$PLAN2` (High).
3. **SQL injection** in the non-parameterized document lookup queries (High).
4. **PDF/SSRF risk**: unescaped narrative content plus raw file-path image references feeding the PDF renderer, which violates the stated PDF-export security requirement (High).
5. Insecure `extract()`/variable-variable patterns and missing audit logging (Medium).

These should block merge until access control is added (verify user authorization for `pid`/`encounter` before rendering), all DB-sourced narrative/plan fields are passed through `text()`, the document lookup queries are parameterized, and the PDF image-loading path is restricted to a mediated, ACL-checked resource resolver rather than raw file paths.