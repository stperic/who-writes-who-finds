## Summary

This change adds a new `$disable_exit` parameter to `C_Document::retrieve_action()` that causes the method to **return raw file bytes to its caller instead of streaming them to the browser with headers and then terminating**. Because of how this controller action is dispatched, this new parameter is directly reachable by an external, unauthenticated-looking request, and it bypasses security-relevant response headers. Combined with a pre-existing, opaque access-control model in the dispatcher, this is a meaningful new attack surface.

---

### 1. Attacker-controlled `$disable_exit` via generic action dispatcher → header bypass → stored/reflected XSS / MIME-sniffing risk
**Location:** `controllers/C_Document.class.php`, new code in `retrieve_action()` (the three new `if ($disable_exit == true) { ... }` blocks), combined with `Controller::act()` in `library/classes/Controller.class.php`.

**OWASP Category:** A03:2021 – Injection (XSS) / A05:2021 – Security Misconfiguration / A01:2021 – Broken Access Control

**Problem:**
`Controller::act()` builds the call to the action method using the *names* of arbitrary query-string parameters as the argument names, and calls the action with
`call_user_func_array(array(&$c_obj, $c_action."_action"), $args_array)`.
Since PHP 8+ treats string-keyed arrays passed to `call_user_func_array()` as **named arguments**, any request containing a parameter literally named `disable_exit` (e.g. `...&document&retrieve&document_id=123&disable_exit=1`) will bind directly to the new `$disable_exit` parameter of `retrieve_action()`. No code change elsewhere is required — this parameter is attacker-reachable today.

When `$disable_exit` is true, the function `return`s before any of the `header('Content-Disposition: ...')`, `header('Content-Type: ...')`, etc. calls execute. The returned string is then echoed back up through `act()`’s `$output` to the HTTP response. Since the response is emitted without a forced-download `Content-Disposition` header and without an explicit `Content-Type`, a browser may sniff the content and render it inline. If a stored document contains HTML/JavaScript (patient-uploaded files are typically attacker-influenced content), this results in **stored XSS** when retrieved through this path, something the original "force download" headers were specifically designed to prevent.

It also silently defeats whatever safeguard the original code had around only ever emitting files through the controlled streaming code path (CSP/Content-Disposition hardening is a common mitigation for document-management XSS, and it is bypassed here).

**Severity:** High

---

### 2. New return path skips audit logging on success (and may now also skip it on an existing failure path)
**Location:** `controllers/C_Document.class.php`, CouchDB branch — `if($disable_exit == true) { return base64_decode($content); }` inserted directly after the error-logging call for the failure case, with no equivalent logging for the success case.

**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures

**Problem:** The function already only logs on failed CouchDB retrieval (`document_upload_download_log`) and not on success; this patch adds yet another silent exit point that returns potentially sensitive document content with zero logging. For a medical records system (patient documents), every successful retrieval of PHI should be logged for audit/compliance (HIPAA-type requirements). This gap pre-dates the change but is made worse because the new code path is one more way to exfiltrate document content without any audit trail.

**Severity:** Medium

---

### 3. Unconditional full-file read into memory (new resource-exhaustion vector)
**Location:** `controllers/C_Document.class.php`, original-file branch:
```php
$f = fopen($url,"r");
$filetext = fread( $f, filesize($url) );
if($disable_exit == true) { return $filetext; }
```
**OWASP Category:** A04:2021 – Insecure Design (resource management) 

**Problem:** Previously, `fread()` was only executed when `$doEncryption` was true; for the normal "stream file to browser" case the file was presumably served without being fully loaded into PHP memory. Now the entire file is unconditionally read into a PHP string variable regardless of whether encryption or `disable_exit` is requested. For large documents (scanned images, PDFs, etc.) this creates an easy memory-exhaustion / DoS vector and removes the efficiency benefit of streaming.

**Severity:** Medium

---

### 4. Logic bug: `disable_exit` branch for converted files returns no content
**Location:**
```php
else{
    $url = $GLOBALS['OE_SITE_DIR'] . '/documents/' . $from_pathname . '/' . $convertedFile;
}
if($disable_exit == true) {
    return ;
}
```
**OWASP Category:** A04:2021 – Insecure Design

**Problem:** In this third code path, when `$disable_exit` is true the function returns `null` without ever reading/returning the converted file’s content. Any caller relying on `disable_exit` to retrieve bytes will silently receive empty data. While this looks like a functional bug rather than a direct vulnerability, silent empty/`null` results are a common source of security bugs downstream (e.g., a caller that checks "did we get data back?" may fail open, treat empty content as "no error", or write out a 0-byte file whose absence goes unnoticed).

**Severity:** Low (reliability bug with potential downstream security impact)

---

### 5. Pre-existing issues touched by this diff (not newly introduced, but relevant)

- **Broken Access Control (unverified):** The visible code never shows an authorization check binding `$patient_id`/`$document_id` to the current session/user before serving file content. If no such check exists earlier in the (unshown) function body, this is a classic IDOR — any authenticated (or possibly unauthenticated) user could retrieve arbitrary documents by ID. This needs to be verified against the full function; it is directly relevant because the new `disable_exit` path reuses the same unauthenticated-looking retrieval logic.
- **Generic action dispatcher (`Controller::act()`) has no authentication/authorization gate** — it will call `<anything>_action` or `<anything>_action_process` on any controller resolved from the URL, driven entirely by untrusted `$_GET`/query-string content, and (as shown above) supports named-argument binding straight from attacker-supplied parameter names. This is a systemic Insecure Design / Broken Access Control issue in the framework that this change relies on and that amplifies finding #1.
- **Passphrase handling:** `$passphrase = $_POST['passphrase'];` is used directly for decryption with no validation, rate-limiting, or brute-force protection — potential Cryptographic Failure / Identification & Authentication Failure if this passphrase is meant to gate access to encrypted documents.
- **No `fclose($f)`** after `fopen()` in the modified code — minor resource-leak, not a direct vulnerability.

---

## Recommendation
- Restrict `$disable_exit` to be an internal-only parameter never settable from user input — explicitly strip/ignore it (and any non-whitelisted parameter) in `Controller::act()`'s argument-binding logic, or switch away from name-based/named-argument binding of attacker-controlled query keys entirely.
- When returning raw content (`disable_exit` true), ensure the calling code still applies the same `Content-Disposition`/`Content-Type` hardening before it is ever sent to a browser.
- Add success/failure audit logging for all document retrieval paths, including the new ones.
- Avoid unconditional full-file reads; keep streaming for the non-encryption case.
- Fix the `return;` bug in the converted-file branch so it returns actual content (or clearly signals failure) instead of `null`.
- Verify and, if missing, add explicit patient/document authorization checks in `retrieve_action()`.