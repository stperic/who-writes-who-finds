## Security review of the `retrieve_action` / `$disable_exit` change

### 1. `disable_exit` is attacker-controllable through the URL (Insecure Design / Broken Access Control)
- **Location:** `retrieve_action(..., $disable_exit=false)` in `C_Document.class.php`, and `Controller::act()` in `Controller.class.php`.
- **Problem:** `Controller::act()` builds the action's arguments from the query string. Every URL parameter name is passed through to `call_user_func_array`, so a request such as `controller.php?document&retrieve&patient_id=1&document_id=5&as_file=true&original_file=true&disable_exit=1` sets the flag.
  - The flag was meant as an internal, programmatic option. It is now a public, user-switchable switch that changes the response path.
  - On PHP 8, the string keys become named arguments, so this works by name. On PHP 5/7 the arguments are positional, so the attacker can supply it as the fifth argument.
  - When the flag is set, the function returns the raw file contents to `act()`. These are appended to `$output` and printed by the caller, without any of the download headers.
- **Severity:** High, because of the consequences below.

### 2. Stored XSS and content sniffing from missing headers (Injection / XSS)
- **Location:** the new early `return` statements, which come before the `header('Content-Type…')`, `Content-Disposition` and `Content-Length` calls.
- **Problem:** The file contents are returned and echoed inline with no `Content-Type`, no `Content-Disposition: attachment`, and no `X-Content-Type-Options: nosniff`. A user who can upload a document (HTML, SVG, or HTML polyglots) can have it rendered in the application's origin. That gives script execution with the victim's session, and in a medical record system that means access to PHI.
- **Severity:** High.

### 3. Bypass of encryption and of the intended output controls (Cryptographic Failures / Security Logging Failures)
- **Location:** the new early returns before the `$doEncryption` branch, and the CouchDB branch.
- **Problem:** Even when the request asks for an encrypted download (`encrypted` / `passphrase`), the early return hands back plaintext.
  - Any audit logging that runs after the file is served (for example `document_upload_download_log`) is also skipped on these paths. This shows in the CouchDB branch, where logging happens only on failure. Retrievals through this path may go unrecorded, and in a HIPAA context that matters.
- **Severity:** Medium.

### 4. Missing authorization check in the touched function (Broken Access Control, pre-existing)
- **Location:** `retrieve_action($patient_id, $document_id, …)`.
- **Problem:** Nothing in the visible code checks that the user may view this patient's documents. It also does not check that `$document_id` belongs to `$patient_id`. Because the new flag makes the function easier to call and reuse, this IDOR risk is more exposed. Verify the ACL check happens before any content is returned.
- **Severity:** High if absent.

### 5. Unchecked `fopen` and full-file read; path and URL handling (Security Misconfiguration / Insecure Design)
- **Location:** `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));`
- **Problems:**
  - Return values are not checked. A failed open produces warnings that may disclose paths, and a zero-byte file makes `fread` fail.
  - The handle is never closed.
  - The whole file is now read into memory on every normal download. Before this change that happened only when encrypting. Large documents or concurrent requests can exhaust memory (DoS).
  - `$url` comes from the database. If a record can be manipulated, `fopen` on a user-influenced value can give local file read through path traversal or `file://`, or even SSRF through wrapper URLs if `allow_url_fopen` is enabled. Validate that the resolved path is inside the documents directory.
- **Severity:** Medium.

### 6. Pre-existing issues in the related controller code
- **`Controller::act()` dispatch:** any `*_action` method on any controller file is callable from the URL, with caller-supplied arguments. This is the root cause of issue 1, so each action must enforce its own authorization.
- **`CONTROLLER_THIS` and `_link()`:** these use `$_SERVER['QUERY_STRING']` and `REQUEST_URI` without encoding. This gives reflected XSS if templates output them unescaped. Severity: Medium.
- **`$_POST['passphrase']` and `encrypt()`:** the passphrase is sent in the request body and the `encrypt()` implementation is not shown. Confirm it uses a modern cipher and mode and a proper KDF. Temporary encrypted files written under `temporary_files_dir` must be deleted. Severity: Low to Medium.

### Recommendation
- Do not expose the flag as a request-reachable parameter. Move the file-reading logic into a separate method that is not an `_action` and has no URL-controlled arguments. Call that method from `retrieve_action` and from the other internal callers.
- Keep the authorization check and the logging in the shared path, so they run in both cases.
- If content must be returned inline, set a safe `Content-Type`, `Content-Disposition: attachment` and `nosniff`.
- Check the `fopen` and `fread` results, close the handle, and stream the file instead of loading it all into memory.