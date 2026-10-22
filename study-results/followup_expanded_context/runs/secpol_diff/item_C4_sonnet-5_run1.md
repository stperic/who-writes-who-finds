# Security Review – `interface/forms/eye_mag/report.php`

## 1. Missing patient-level authorization check (IDOR)
**Location:** Top of file / `eye_mag_report()` / `narrative()` — `$pid = $_REQUEST['ptid']`, `$encounter = $_REQUEST['encid']`, `$form_id = $_REQUEST['formid']` are taken directly from the request and used to pull and render a full clinical report (HPI, exam findings, refraction, patient photo, impression/plan, provider signature).

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** `globals.php` only confirms the user is *authenticated*; there is no call to `acl_check()`, `verify_patient_access()`, or any comparison with `$_SESSION['pid']`/encounter ownership to confirm the logged-in user is actually authorized to view *this* patient's record. Any authenticated user can change `ptid`/`encid`/`formid` in the URL and view another patient's full eye exam, photo, and clinical notes (horizontal privilege escalation / IDOR). This is the most serious issue in the file, since it governs access to PHI.

**Severity:** Critical

---

## 2. SQL Injection in `display_draw_image()`
**Location:**
```php
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
`$base_name` is built from `$pid` and `$encounter`, both taken straight from `$_REQUEST`.

**OWASP Category:** A03:2021 – Injection

**Problem:** Unlike almost every other query in this file (which correctly use `sqlStatement($query, array(...))` placeholders), this query concatenates request-derived values directly into the SQL string with no bound parameters. Even with `$sanitize_all_escapes = true` (OpenEMR's legacy auto-escaping of superglobals), this only mitigates quote-breakout injection — it does not prevent SQL `LIKE` wildcard abuse (`%`, `_`), so an attacker can craft `ptid`/`encid` values containing wildcards to broaden the match and retrieve document records (and therefore images) belonging to *other* patients/encounters, independent of the IDOR issue above. This should use a parameterized query exactly like the rest of the file.

**Severity:** High

---

## 3. Non-parameterized SQL using session data
**Location:**
```php
if ($_SESSION['pc_facility']) {
   $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
} else {
   $sql = "SELECT * FROM facility ORDER BY billing_location DESC LIMIT 1";
}
$facility = sqlQuery($sql);
```

**OWASP Category:** A03:2021 – Injection

**Problem:** Directly concatenates a session value into SQL instead of using a bound parameter. While `pc_facility` is not directly attacker-supplied in this request, it is still inconsistent with secure coding practice used elsewhere in the same file, and session values can sometimes be influenced through other vulnerable code paths. Should be `sqlQuery($sql, array($_SESSION['pc_facility']))`.

**Severity:** Medium

---

## 4. Stored XSS – unescaped HPI field
**Location:**
```php
<b><?php echo xlt('HPI'); ?>:</b>   
&nbsp;<?php echo $HPI1; ?>
```

**OWASP Category:** A03:2021 – Injection (Cross-Site Scripting)

**Problem:** Nearly every other field in the report is wrapped in `text()` before output (e.g., `$CC1`, `$HPI2`, `$HPI3` are escaped), but `$HPI1` — which comes straight from the database via `extract()` of a patient-entered field — is echoed raw. If this field contains HTML/JS (entered through the clinical UI or via another injection), it will execute in the browser of anyone viewing the report (stored XSS), and could also corrupt PDF generation.

**Severity:** High

---

## 5. Stored XSS – Impression/Plan fields
**Location:**
```php
if ($item['codetext'] > '')  {
    echo $item['codetext']."<br />";
} else {
    ...
    echo $item['code']."<br />";
}
echo  $item['plan']."</div><br />";
```
and
```php
$PLAN_items = explode('|',$PLAN);
foreach ($PLAN_items as $item) {
    echo  $item."<br />";
}  
if ($PLAN2) {
    echo $PLAN2."<br />";
}
```

**OWASP Category:** A03:2021 – Injection (XSS)

**Problem:** `codetext`, `code`, `plan`, `PLAN`, and `PLAN2` are database-stored free-text fields rendered without any escaping (`text()`/`htmlspecialchars()`), unlike `item['title']` on the preceding line which is correctly escaped. The `str_replace()` on newline characters does not neutralize HTML. This is a stored XSS vector that can execute in the context of any user (including higher-privileged staff) who views this report.

**Severity:** High

---

## 6. Weak/inconsistent output encoding helper
**Location:**
```php
function report_ACT($term) {
  $term = nl2br(htmlspecialchars($term,ENT_NOQUOTES));
  return $term."&nbsp;";
}
```

**OWASP Category:** A03:2021 – Injection (XSS) / Security Misconfiguration

**Problem:** Uses `ENT_NOQUOTES`, which leaves single and double quotes un-encoded. While currently only used in text-node contexts, this is an easy-to-misuse helper that diverges from the framework's standard `text()`/`attr()` escaping functions, and is risky if reused elsewhere (e.g., inside an attribute).

**Severity:** Low

---

## 7. Use of `extract()` on DB result sets and dynamic variable variables
**Location:** `@extract($objQuery);`, `@extract($encounter_data);`, and the preferences loop:
```php
while ($prefs= sqlFetchArray($result))   {    
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
```
and dynamic refraction variables such as `${"ODSPH_$count_rx"} = ...`.

**OWASP Category:** A04:2021 – Insecure Design

**Problem:** `extract()` and variable-variables (`$$LOCATION`) create PHP variables named from database content. If an attacker can influence row data (e.g., via the SQL injection above, a compromised account, or a crafted `LOCATION` preference value), they could potentially overwrite security-relevant variables already in scope (`$choice`, `$form_folder`, `$PDF_OUTPUT`, etc.), leading to logic bypass or further injection. This pattern should be replaced with explicit variable assignment.

**Severity:** Medium

---

## 8. Silent error suppression / no audit logging of PHI access
**Location:** Throughout, e.g. `@extract(...)`, no logging calls anywhere in the file when a report is generated/viewed.

**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures

**Problem:** The `@` operator suppresses PHP warnings/notices (e.g., failed queries, undefined variables), hiding failures that could indicate attempted abuse (e.g., probing for other patients' encounters). There is also no audit-trail entry generated when a user views a patient's full clinical report/photo, which is normally expected for PHI access in a HIPAA-regulated system such as OpenEMR.

**Severity:** Medium

---

## 9. Information disclosure via raw filesystem paths
**Location:**
```php
if ($PDF_OUTPUT) {
  echo "<img src='". $from_file."' style='width:220px;'>";
}
```
(`$from_file` built from `$GLOBALS["fileroot"] . "/sites/" . $_SESSION['site_id'] . '/documents/' ...`)

**OWASP Category:** A05:2021 – Security Misconfiguration

**Problem:** Absolute server filesystem paths are embedded directly into HTML output. This is presumably intended only for internal PDF-rendering consumption, but if this code path is ever reached outside of the PDF generator (or an error causes `$PDF_OUTPUT` to be mis-set), it discloses internal directory structure to the client.

**Severity:** Low

---

## 10. Lack of input validation / fail-open behavior
**Location:** `narrative()` / `eye_mag_report()` — no check that `sqlQuery()` actually returned a row before continuing to render the page.

**OWASP Category:** A04:2021 – Insecure Design

**Problem:** If `$pid`/`$encounter` don't correspond to a real record (e.g., invalid/nonexistent/unauthorized IDs), the script does not stop or return an error — it continues executing with mostly empty variables and still renders a (mostly blank) report shell. Combined with the missing authorization check, this makes it harder to detect/alert on access attempts for non-existent or unauthorized records.

**Severity:** Low

---

## Summary

The most serious problems are:
1. **No authorization check tying the requested `ptid`/`encid`/`formid` to the logged-in user's permitted patients** — a critical Broken Access Control / IDOR vulnerability exposing PHI for arbitrary patients.
2. **A SQL injection via string concatenation** in `display_draw_image()`, inconsistent with the parameterized queries used elsewhere in the same file.
3. **Multiple stored XSS vulnerabilities** from inconsistent output encoding (`$HPI1`, Impression/Plan `code`/`codetext`/`plan`, `$PLAN`/`$PLAN2`).

Secondary issues include use of `extract()`/variable-variables, non-parameterized use of session data in SQL, weak escaping helpers, silent error suppression, absence of audit logging for PHI access, and minor information disclosure of server paths. These should all be addressed before merge, with priority on #1 and #2 given the direct risk to patient data confidentiality.