# Security Review: `C_Document::retrieve_action()` (disable_exit change)

**Verdict:** The change introduces a flag that can return document contents to the caller and skips the download-encryption step. It should not merge until the flag is confirmed unreachable from user input and the encryption bypass is fixed. Several issues in the touched code also predate this diff.

## Findings

### 1. Encryption bypass: plaintext returned when `$doEncryption` is set
- **Location:** `retrieve_action`, the new `if($disable_exit == true) { return $filetext; }` in the `$original_file` branch, and the CouchDB branch `return base64_decode($content);`
- **OWASP:** A02:2021 Cryptographic Failures; A04:2021 Insecure Design
- **Problem:** The early returns run before the `if ( $doEncryption )` block. If the user requested an encrypted download (`$_POST['encrypted']`), a caller using `disable_exit=true` gets the raw, unencrypted document. The encryption requirement is silently skipped.
- **Severity:** High (if the flag is reachable from a request) / Medium (if only internal callers use it)

### 2. Unauthenticated-style flag can change response behavior
- **Location:** New signature `retrieve_action($patient_id="",$document_id,$as_file=true,$original_file=true,$disable_exit=false)`
- **OWASP:** A01:2021 Broken Access Control; A04:2021 Insecure Design
- **Problem:** `disable_exit` changes whether the function streams the file and terminates, or returns its contents. If the controller dispatcher maps `$_GET`/`$_POST`/`$_REQUEST` values onto action arguments, an attacker can set `disable_exit=1` and receive content through whatever path calls the function. The diff does not show the dispatcher, so this must be verified. Security-sensitive behavior should not be selected by a boolean parameter that might be request-controlled. Use an internal method or a private helper that the request layer cannot reach.
- **Severity:** High if request-reachable; otherwise Low

### 3. Unconditional file read before the authorization-sensitive path
- **Location:** `$f = fopen($url,"r"); $filetext = fread( $f, filesize($url) );` moved above the header calls and the encryption branch
- **OWASP:** A05:2021 Security Misconfiguration (error handling); A04:2021 Insecure Design
- **Problems:**
  - The file is now read into memory for every non-encrypted download, not only when encryption is requested. Large documents can exhaust `memory_limit` and cause a fatal error or denial of service (A04).
  - `fopen` is not checked for failure. If it fails, `filesize` and `fread` produce warnings or errors and `$filetext` may be `false`. The error may disclose the server path.
  - The handle `$f` is never `fclose`d in the new code path, which leaks file descriptors.
- **Severity:** Medium

### 4. Predictable temporary file for encrypted output (pre-existing, touched area)
- **Location:** `$tmpfilename = "/encrypted_".$d->get_url_file();` written under `$GLOBALS['temporary_files_dir']`
- **OWASP:** A01:2021 Broken Access Control; A08:2021 Software and Data Integrity Failures
- **Problem:** The name is predictable and derived from the stored filename. Other local users or processes can pre-create a symlink or read the file while it exists. The diff does not show cleanup. If the file is not deleted after download, ciphertext (and possibly plaintext in other paths) remains on disk. Use `tempnam()`/`random_bytes()`-based names with restrictive permissions (0600) and delete the file after use.
- **Severity:** Medium

### 5. Path traversal risk via stored filename (cannot be fully verified)
- **Location:** `$url` built from `$from_pathname` and `$convertedFile`, and `$d->get_url_file()`
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The diff relies on `$url` built from database fields and then calls `fopen`. If any component can contain `../` or absolute paths (for example, from upload metadata), the function can read arbitrary files. Validate that the resolved `realpath($url)` lies within the documents directory.
- **Severity:** Medium (unverified)

### 6. Missing authorization check in the touched function (pre-existing)
- **Location:** Start of `retrieve_action`, where `$patient_id` and `$document_id` are used
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The diff does not show an ACL check (`acl_check`) or a check that `$document_id` belongs to `$patient_id`. If the caller does not verify this, IDOR is possible. Confirm that the check runs before any of the new return paths.
- **Severity:** High (unverified)

### 7. Cryptographic strength and passphrase handling (pre-existing, relies on unchanged code)
- **Location:** `$this->encrypt($filetext, $passphrase)` and `$passphrase = $_POST['passphrase']`
- **OWASP:** A02:2021 Cryptographic Failures; A09:2021 Logging Failures
- **Problem:** The cipher, key derivation, IV handling, and integrity protection of `encrypt()` are not visible. Passphrases sent in POST must be protected by TLS. Check that the passphrase is not logged (including in `document_upload_download_log`), is not stored, and that the scheme uses an authenticated mode (e.g., AES-256-GCM) with a PBKDF2/Argon2 KDF.
- **Severity:** Medium (unverified)

### 8. Missing error handling on failure paths (code quality, security-adjacent)
- **Location:** `return ;` in the converted-file branch and `return base64_decode($content);`
- **OWASP:** A04:2021 Insecure Design
- **Problem:** `return;` yields `null` and `base64_decode` may return `false` on invalid input. Callers that do not check these may treat failure as success or output empty content. Prefer explicit error values and log failures.
- **Severity:** Low

### 9. Function signature defect
- **Location:** `retrieve_action($patient_id="",$document_id,...)`
- **OWASP:** A04:2021 Insecure Design (maintainability)
- **Problem:** An optional parameter precedes a required one. PHP 8 deprecates this, and the default for `$patient_id` is effectively ignored. This can cause callers to pass arguments into the wrong slots, which may matter for the authorization checks in item 6.
- **Severity:** Low

## Summary

| # | Issue | OWASP | Severity |
|---|---|---|---|
| 1 | `disable_exit` returns plaintext, bypassing encryption | A02, A04 | High/Medium |
| 2 | Boolean flag controls response behavior; may be request-reachable | A01, A04 | High if reachable |
| 3 | Whole-file read, unchecked `fopen`, leaked handle | A04, A05 | Medium |
| 4 | Predictable temp file for encrypted output | A01, A08 | Medium |
| 5 | Possible path traversal via `$url` | A01 | Medium (unverified) |
| 6 | No visible ACL/ownership check | A01 | High (unverified) |
| 7 | Encryption scheme and passphrase handling unknown | A02, A09 | Medium (unverified) |
| 8 | Unchecked failure returns | A04 | Low |
| 9 | Optional parameter before required parameter | A04 | Low |

## Recommended Actions
1. Remove `disable_exit`. Put the content-returning logic in a private helper that the request dispatcher cannot reach, and call it only from trusted code.
2. Move the encryption decision before any early return so no plaintext is returned when encryption was requested.
3. Confirm the ACL check and document-to-patient ownership check run before any branch.
4. Use `realpath()` to confirm `$url` stays inside the documents directory.
5. Check `fopen` results, close handles, and stream large files instead of loading them whole.
6. Replace the temp filename with a random name, create it with mode 0600, and delete it after use.
7. Review `encrypt()` for an authenticated cipher and a proper KDF, and confirm the passphrase is never logged.