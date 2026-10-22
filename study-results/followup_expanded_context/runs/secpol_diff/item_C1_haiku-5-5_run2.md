## Security review: `C_Document::retrieve_action` (new `$disable_exit` parameter)

The diff adds a `$disable_exit` flag that makes `retrieve_action` return file contents or stop early instead of streaming the download and exiting. The main risk depends on how this action is reached, which the diff does not show.

### Finding 1: Caller-controlled bypass of the download path
- **Location:** `retrieve_action($patient_id="", $document_id, $as_file=true, $original_file=true, $disable_exit=false)`, and the three `if($disable_exit == true)` branches (CouchDB branch, original-file branch, and the converted-file branch).
- **OWASP category:** A01:2021 Broken Access Control (with A04 Insecure Design).
- **Problem:** If the controller dispatcher maps request parameters positionally or by name onto action arguments (common in OpenEMR-style `$c->action($_REQUEST...)` dispatch), an attacker can send `disable_exit=1` and receive the decrypted or raw document as a return value. Any code path that then echoes or stores that value sends the file out without the normal headers and without any code path that might have been added to end the request. The flag is also a general "skip the response" switch that any caller can enable, which is an unsafe design even when no current caller misuses it.
- **Severity:** High if the dispatcher exposes arguments from the request. Low if only internal PHP code can call this method. Verify the dispatcher before merging.
- **Recommendation:** Do not expose this as a method parameter. Move the content-return logic into a separate internal method that is not reachable from the request dispatcher, or strip/ignore arguments that come from request data. Only internal code should be able to set the flag.

### Finding 2: Possible audit-log bypass
- **Location:** The early `return` statements in the new `disable_exit` branches.
- **OWASP category:** A09:2021 Security Logging and Monitoring Failures.
- **Problem:** The early returns skip the rest of the function. If the success-path call to `document_upload_download_log()` (or any other audit call) comes after these branches, a retrieval through the flag is never recorded. The diff does not show whether logging happens on the success path.
- **Severity:** Medium (verify the success path).
- **Recommendation:** Log the access before any early return, or place the logging call before the branch.

### Finding 3: Authorization not visible in the diff (pre-existing, verify)
- **Location:** Start of `retrieve_action`, where `$patient_id` and `$document_id` are used to load the document.
- **OWASP category:** A01:2021 Broken Access Control (IDOR).
- **Problem:** The action takes a `$document_id` and loads the document. The diff does not show an ACL check (for example `acl_check('patients','docs')`) or a check that the document belongs to `$patient_id`. Without one, any authenticated user could retrieve any document by ID. Because `$patient_id` has a default of `""`, a missing patient binding would make this worse.
- **Severity:** High if no check exists. Confirm that the check runs before the code this diff touches.
- **Recommendation:** Enforce `acl_check` for the document category and verify `$document->get_foreign_id() == $patient_id` before serving content.

### Finding 4: Unchecked `fopen()` and resource leak (introduced by this change)
- **Location:** `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));`
- **OWASP category:** A04:2021 Insecure Design / A05:2021 Security Misconfiguration (error handling).
- **Problem:** The `fopen()` return value is not checked. If the file is missing or unreadable, `fopen` returns `false`. `filesize()` then emits a warning, and `fread(false, …)` fails. Warnings can expose server paths in responses if `display_errors` is on. The handle is also never closed (`fclose`). The file is now read before the `$doEncryption` branch and before the headers are sent, so this path runs on every request, not only encrypted ones.
- **Severity:** Low.
- **Recommendation:** Check `$f === false` and fail with a generic error, use `file_get_contents()` or `fclose($f)` after reading, and read only once.

### Finding 5: Unsanitized filename in temp path (pre-existing)
- **Location:** `$tmpfilename = "/encrypted_".$d->get_url_file();` in the `$doEncryption` branch.
- **OWASP category:** A03:2021 Injection (path traversal) / A01:2021.
- **Problem:** `get_url_file()` comes from the database. If upload sanitization is weak, a stored name containing `../` could write the ciphertext outside the temp directory. The impact depends on upload-time sanitization, which is not in this diff.
- **Severity:** Low to Medium, depending on upload sanitization.
- **Recommendation:** Apply `basename()` and a strict character allowlist to the name, and confirm the resolved path stays inside `$GLOBALS['temporary_files_dir']`.

### Finding 6: Encryption strength and passphrase handling (pre-existing, cannot assess)
- **Location:** `$this->encrypt($filetext, $passphrase)` and `$passphrase = $_POST['passphrase']`.
- **OWASP category:** A02:2021 Cryptographic Failures.
- **Problem:** The diff does not show `encrypt()`. A user-supplied passphrase used directly as a key, without a salted KDF (PBKDF2, scrypt, or Argon2), or with a non-AEAD mode such as unauthenticated CBC or ECB, would be weak. Passphrases also travel in POST bodies and may be logged by proxies or web servers if misconfigured.
- **Severity:** Medium (unverified).
- **Recommendation:** Review `encrypt()`/`decrypt()`. Use an authenticated cipher (AES-256-GCM) with a random salt and IV and a memory-hard KDF.

### Finding 7: Memory exhaustion (pre-existing, low)
- **Location:** `fread($f, filesize($url))` and `base64_decode($content)` on the whole file.
- **OWASP category:** A04:2021 Insecure Design (resource exhaustion).
- **Problem:** Large documents are fully loaded into memory, and the new return path returns the full string to the caller.
- **Severity:** Low.
- **Recommendation:** Stream the file in chunks where possible.

### Summary
| # | Issue | Category | Severity |
|---|---|---|---|
| 1 | `$disable_exit` lets callers get raw file content and skip the response | A01 / A04 | High if request-reachable, else Low |
| 2 | Early returns may skip audit logging | A09 | Medium (verify) |
| 3 | No visible ACL/ownership check on document retrieval | A01 (IDOR) | High if absent (verify) |
| 4 | Unchecked `fopen`, unclosed handle, file read before headers | A04 / A05 | Low |
| 5 | Unsanitized DB filename in temp path | A03 / A01 | Low–Medium |
| 6 | Passphrase-based encryption strength unknown | A02 | Medium (verify) |
| 7 | Whole-file memory load | A04 | Low |

**Recommendation:** Do not merge until Finding 1 is resolved. Confirm how the dispatcher passes arguments, and confirm that `acl_check` and the patient-ownership check run before the new code. Findings 4 and 5 are easy fixes that should go in the same change.