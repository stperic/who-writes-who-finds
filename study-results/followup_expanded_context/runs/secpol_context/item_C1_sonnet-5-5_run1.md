## Security review of the `retrieve_action` / `$disable_exit` change

### 1. `disable_exit` is user-controllable and bypasses the download headers (stored XSS)
- **Location:** `retrieve_action(..., $disable_exit=false)` and the three new `if ($disable_exit == true) return ...` blocks. The dispatch happens in `Controller::act()`.
- **OWASP:** A03 Injection (XSS), A05 Security Misconfiguration, A04 Insecure Design
- **Problem:**
  - `Controller::act()` builds the action's arguments from the request's query-string keys and calls `call_user_func_array` on the action. Any new parameter on an `*_action` method is therefore attacker-controllable. The PR intends `$disable_exit` as an internal flag for other PHP callers, but a user can request `controller.php?document&retrieve&patient_id=1&document_id=5&disable_exit=true`. This is positional on older PHP and by name on PHP 8.
  - When the flag is set, the function returns the raw file bytes before any `Content-Type`, `Content-Disposition` or `Content-Length` header is sent. `act()` appends the return value to `$output`, which is then echoed.
  - The response defaults to `text/html`, so an uploaded `.html`, `.svg` or similar file executes as script in the application's origin. That gives stored XSS and session-riding against clinicians, in a PHI system.
  - Previously the file was served with its own MIME type and as an attachment. The `X-Content-Type-Options` header is not set anywhere either.
- **Severity:** High
- **Fix:**
  - Do not expose the flag as a routable argument. Split the logic into a private or protected method such as `get_document_contents()`, and have `retrieve_action` call it and send headers.
  - Alternatively, ignore or strip `disable_exit` when it comes from the request.
  - Always send `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`.

### 2. Whole files are read into memory, with no error handling or handle cleanup
- **Location:** the new `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));` block.
- **OWASP:** A04 Insecure Design (availability), A05 Security Misconfiguration
- **Problem:**
  - The read now runs for every normal download, not only the encryption branch. Large documents are loaded entirely into memory, so repeated requests can exhaust it (DoS).
  - `fopen` is not checked for failure.
  - `fread` with a length of 0 (an empty file) raises a warning, or an error on PHP 8.
  - The handle is never closed.
  - Failures can leak filesystem paths through PHP warnings if `display_errors` is on.
- **Severity:** Medium/Low
- **Fix:** Check the return values, close the handle, and stream (`readfile` / `fpassthru`) when no encryption is needed.

### 3. Pre-existing: no visible authorization on document retrieval (IDOR)
- **Location:** `retrieve_action($patient_id, $document_id, ...)` and `Controller::act()`.
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - The action takes `patient_id` and `document_id` straight from the URL. Nothing in the code shown checks that the user is allowed to access that patient or document, or that the document belongs to that patient. Any authenticated user (or anyone, if the controller entry point lacks an ACL check) may be able to enumerate documents.
  - The new flag makes this easier to abuse, because the content is returned inline without the download-oriented headers.
- **Severity:** High if confirmed. Verify the ACL checks in `controller.php` and the action.

### 4. Pre-existing: weak input and design practices in the dispatcher
- **Location:** `Controller::act()` and `retrieve_action`.
- **OWASP:** A04 Insecure Design, A02 Cryptographic Failures
- **Problem:**
  - `act()` exposes every public `*_action` method and every argument to the URL, so adding parameters silently widens the attack surface (see #1).
  - The passphrase and encryption flag come from `$_POST`, and `$this->encrypt` is used on the plaintext. It is unclear whether this uses a vetted cipher and mode.
  - The path in `$url` is derived from stored data and is used with `fopen`. If it can be influenced, there is a path traversal or SSRF-style risk through wrappers, and the path should be validated.
- **Severity:** Medium

### 5. Logging
- **Location:** the early returns in the CouchDB and file branches.
- **OWASP:** A09 Security Logging and Monitoring Failures
- **Problem:** The early returns skip any later download-audit logging, so reads made with the flag may go unrecorded. Make sure the access is logged before returning.
- **Severity:** Low/Medium

**Recommendation:** Do not merge as is. Fix #1 first, by moving the "return content" behavior out of the request-routable action, and verify #3.