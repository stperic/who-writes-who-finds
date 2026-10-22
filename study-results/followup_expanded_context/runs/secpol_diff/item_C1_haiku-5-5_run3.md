# Security Review: `C_Document::retrieve_action` (disable_exit change)

I reviewed only the hunks shown. Several conclusions depend on code outside the diff (the dispatcher, the ACL check, and `encrypt()`), so I flag those as dependencies rather than confirmed flaws.

## Findings

### 1. Caller-controlled bypass of response handling (Broken Access Control / Insecure Design)
- **Location:** Signature change at line ~386 (`$disable_exit=false`), used in the three new `if($disable_exit == true)` blocks.
- **Category:** A01:2021 Broken Access Control, A04:2021 Insecure Design
- **Problem:** The new parameter switches the action from "stream to the client and `die()`" to "return the raw decrypted document bytes to the caller." If the controller dispatcher maps request parameters onto method arguments (common in OpenEMR-style `act()` routing), a user could pass `disable_exit=true` in the URL or POST body. The file would then be returned into a code path that may echo or render it, or may continue execution with the document in memory. Any future caller that passes the return value to output would expose documents.
- **Severity:** High if the dispatcher forwards request data to this method. Low if only internal code can call it. I could not verify which applies.
- **Fix:** Do not expose this as a request-controllable argument. Use an internal-only method (e.g., a private `_fetchDocumentContent()`) that the streaming action calls, or strictly cast and validate the flag and confirm it is never sourced from `$_GET`/`$_POST`/`$_REQUEST`.

### 2. Entire file read into memory before the response path (Security Misconfiguration / DoS, A05/A04)
- **Location:** `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));` (moved above the header block).
- **Category:** A04:2021 Insecure Design (resource exhaustion)
- **Problem:** The file is now read fully into memory for every request, including the normal non-encrypted download path, which previously streamed. Large documents can exceed `memory_limit` and cause fatal errors or repeated requests can exhaust server memory. An authenticated user can trigger this repeatedly.
- **Severity:** Medium
- **Fix:** Keep streaming for the plain download path (`fpassthru`/`readfile`) and only read into memory when encryption is actually required.

### 3. Unchecked `fopen` and unclosed handle (Security Misconfiguration / Error Handling, A05/A09)
- **Location:** The new `fopen($url,"r")` line.
- **Category:** A05:2021 Security Misconfiguration, A09:2021 Logging and Monitoring Failures (partially)
- **Problem:**
  - The return value of `fopen` is not checked. If the file is missing or unreadable, `fread(false, filesize($url))` raises warnings. With `display_errors` enabled, these disclose the server filesystem path.
  - `$f` is never closed in the paths where the function returns early (`return $filetext;`), so file descriptors leak on repeated calls.
- **Severity:** Low to Medium (Medium if `display_errors` is on in production)
- **Fix:** Check `if ($f === false) { log; die/return error }`, call `fclose($f)` on every exit path, and suppress or handle `filesize` failures.

### 4. Early returns may skip audit logging (Logging and Monitoring Failures, A09:2021)
- **Location:** The three `disable_exit` returns, particularly the CouchDB one and the original-file one.
- **Category:** A09:2021
- **Problem:** Success-path logging (for example `document_upload_download_log`) normally runs just before the `die()`/`exit`. If the success log call sits after these new early returns, document retrieval through the `disable_exit` path goes unaudited. I can't confirm this from the diff.
- **Severity:** Medium (conditional)
- **Fix:** Ensure the access/audit log is written before any early return, so every document read is recorded.

### 5. Dependencies on existing code this change relies on (not introduced here, but in scope)
These pre-existing issues sit in the code paths this change touches and should be verified:

- **a. Authorization check is not visible in the diff (A01:2021).** The function trusts `$patient_id` and `$document_id` (note the `$patient_id=""` default placed before a required parameter). Confirm that an ACL check (for example `acl_check('patients','docs')`) and a patient/document ownership check run before any of the read/return paths. The early return bypasses everything after it, so the check must sit above it.
- **b. User-supplied passphrase used for encryption (A02:2021 Cryptographic Failures).** `$passphrase = $_POST['passphrase']` drives `$this->encrypt()`. Verify that `encrypt()` uses an authenticated cipher (for example AES-256-GCM), derives keys with a KDF such as PBKDF2/Argon2 with a per-message salt, and generates a random IV. A static IV, ECB mode, or a raw passphrase as key would be a critical flaw.
- **c. Predictable temporary file path (A01/A05).** `$tmpfilename = "/encrypted_".$d->get_url_file();` writes to a predictable name in `$GLOBALS['temporary_files_dir']`. This invites symlink attacks and collisions between users. Use `tempnam()`/`random_bytes()` and confirm the file is deleted after use.
- **d. Path handling for `$url` (A01:2021 Path Traversal).** `$url` is built from `$from_pathname` and `$convertedFile`. Confirm these are derived from DB values and sanitized (no `..` or absolute paths) before `fopen`.

## Summary

| # | Issue | Category | Severity |
|---|-------|----------|----------|
| 1 | `disable_exit` may be request-controllable, returning raw document bytes | A01 / A04 | High (if routable) |
| 2 | Whole file read into memory on every download | A04 (DoS) | Medium |
| 3 | Unchecked `fopen`, leaked handle, path disclosure on error | A05 / A09 | Low–Medium |
| 4 | Early returns may skip audit logging | A09 | Medium (conditional) |
| 5 | Verify ACL, passphrase crypto, temp file handling, path sanitization | A01 / A02 | Depends on existing code |

**Recommendation:** Do not merge until item 1 is resolved. Confirm that `disable_exit` cannot be set from request input. Fix items 2 and 3 in the same change, since they are in lines you are already modifying, and verify item 4 and the dependencies in item 5.