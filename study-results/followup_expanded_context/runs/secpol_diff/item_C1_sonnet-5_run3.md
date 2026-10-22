## Security Review – `controllers/C_Document.class.php` (`retrieve_action`)

### 1. Broken Access Control – new `$disable_exit` bypass path
**Location:** `retrieve_action()` signature and all three new `if ($disable_exit == true) { return ...; }` blocks.
**OWASP Category:** A01:2021 – Broken Access Control
**Problem:** The function previously always ended the request by streaming the file with download headers (and typically terminating). The new parameter adds an alternate code path that returns raw document bytes (or base64-decoded CouchDB content) directly to the caller, in‑process, with no headers and no forced exit. There is no visible authorization/ownership check in this function tying `$patient_id`/`$document_id` to the current authenticated user's access rights. If any new caller invokes `retrieve_action(..., true)` without independently re-validating that the current user is allowed to access that specific patient's document, this creates a trivial way to read arbitrary documents in-process (e.g., for export/print features, APIs, etc.). Because the diff doesn't show the new call site(s), this must be verified — but the function itself still doesn't enforce access control.
**Severity:** High (pending verification of all new callers)

### 2. Security Logging and Monitoring Failure – successful retrieval not logged on new path
**Location:** All three `return` statements added under `$disable_exit`.
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
**Problem:** The failure path explicitly calls `document_upload_download_log(...)` before dying. The new success-return paths skip straight to `return` with no equivalent audit log call. For a medical records system, every access/download of a patient document should be auditable (HIPAA-relevant). This new code path silently exfiltrates document content without creating an audit trail.
**Severity:** Medium–High

### 3. Insecure Design – returned content lacks context/sanitization for reuse
**Location:** `return base64_decode($content);` and `return $filetext;`
**OWASP Category:** A04:2021 – Insecure Design (potentially leading to A03 Injection/XSS downstream)
**Problem:** Raw binary/file content is now handed back to arbitrary calling code without any indication of MIME type, without the `Content-Disposition`/`Content-Type` headers that were used to force a safe download. If any caller echoes this content into an HTML response, email, or log without proper content-type handling/encoding, it could result in XSS or MIME-sniffing attacks (e.g., an uploaded HTML/SVG document served inline). This needs to be validated at every new call site.
**Severity:** Medium (contingent on caller behavior — flag for follow-up)

### 4. Logic bug in “converted file” branch returns `NULL` instead of content
**Location:**
```php
if($disable_exit == true) {
    return ;
}
```
**OWASP Category:** Not a classic OWASP category, but relevant to A04 (Insecure Design) since silent `NULL` could be misinterpreted by calling code as "no error / empty but valid" rather than "failed to fetch", potentially causing callers to skip expected security checks (e.g., assuming success where no content was actually retrieved).
**Severity:** Low, but should be fixed for correctness/security-adjacent reasons.

### 5. Pre-existing: Unvalidated file path used with `fopen`
**Location:**
```php
$f = fopen($url,"r");
$filetext = fread( $f, filesize($url) );
```
**OWASP Category:** A01:2021 – Broken Access Control / Path Traversal (A03-adjacent)
**Problem:** `$url` is built from document metadata tied to `$document_id`/`patient_id`. This code was already present, but the diff now executes the `fopen`/`fread` unconditionally (previously it only ran inside the encryption branch) and exposes the resulting content through the new `return` path. If `$document_id` or stored filename/path values are not strictly validated against the owning patient/user and are not protected against `../` traversal, this enables arbitrary file disclosure. No error handling exists if `fopen` fails (`$f === false`), which will also throw a PHP warning (info disclosure risk if `display_errors` is on).
**Severity:** High (pre-existing, but increased exposure through new in-process return path)

### 6. Pre-existing: User-supplied passphrase used as encryption key material
**Location:**
```php
$passphrase = $_POST['passphrase'];
...
$ciphertext = $this->encrypt( $filetext, $passphrase );
```
**OWASP Category:** A02:2021 – Cryptographic Failures
**Problem:** The passphrase comes straight from POST data with no apparent strength validation or KDF before being used as key material for `encrypt()`. This predates the diff but is directly inside the function being modified/extended, and now the plaintext (`$filetext`) is also exposed via the new return path, compounding the risk if the encryption itself is weak.
**Severity:** Medium (pre-existing)

### 7. General: No authentication/CSRF context shown for `$_POST['encrypted']` / `$_POST['passphrase']`
**Location:** Top of `retrieve_action`
**OWASP Category:** A01/A07 – Broken Access Control / Identification & Authentication Failures
**Problem:** Not part of this diff, but worth flagging since the function is being extended: there is no visible check in the shown code that the request is authenticated/authorized for the given `$patient_id` before documents are read and potentially decrypted. If such checks exist elsewhere in the controller (not shown), ensure they also cover the new `$disable_exit=true` invocation paths.
**Severity:** Medium (needs confirmation from surrounding code not shown in diff)

---

## Summary
The diff's main new risk is architectural: it converts a "stream-to-browser-and-exit" function into one that can also return raw document bytes to arbitrary internal callers, **without adding any new access-control check or audit logging for that path**. Combined with pre-existing weaknesses (unauthenticated-looking file path construction, user-supplied encryption passphrase), this significantly increases the blast radius if any new caller fails to independently enforce authorization and logging.

**Recommendations:**
- Ensure every caller using `disable_exit=true` performs its own authorization check verifying the current user may access `$patient_id`/`$document_id` before calling this function, or better, perform the check inside `retrieve_action` itself regardless of `$disable_exit`.
- Add an audit-log call on the success path, not just on failure.
- Fix the `return;` bug in the converted-file branch to actually return content (or clearly document that the converted-file variant returns via a different mechanism).
- Validate/sanitize `$url`/file paths to prevent path traversal and confirm ownership of the file.
- Review and harden the encryption passphrase handling (server-generated key or proper KDF, not raw POST value).