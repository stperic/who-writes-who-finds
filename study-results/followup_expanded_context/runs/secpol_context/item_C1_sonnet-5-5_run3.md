## Security review of the `retrieve_action` change in `C_Document.class.php`

### 1. Attacker-controlled `$disable_exit` flag changes the download path (new in this PR)
- **Location:** `retrieve_action(..., $disable_exit=false)` and the three new `if ($disable_exit == true) return ...` blocks (CouchDB branch, the original-file branch, and the converted-file branch).
- **OWASP:** A04 Insecure Design, A05 Security Misconfiguration. It also enables XSS (A03) and weakens A09 logging.
- **Problem:** `Controller::act()` passes every URL query parameter as an argument to the action through `call_user_func_array`. The new parameter is therefore reachable from the request, for example `controller.php?document&retrieve&patient_id=1&document_id=5&disable_exit=true`. The flag was meant to be an internal, programmatic option, but any authenticated user can now set it.
  - When it is set, the function returns the raw file bytes into `$output`, and the front controller then echoes them. The code skips every safety header: `Content-Type`, `Content-Disposition`, and the `Content-Description` / `Cache-Control` headers. Without them the browser falls back to `text/html` or sniffs the type.
  - A user-uploaded HTML, SVG or JS document is then rendered inline in the application's origin. This is **stored XSS** and can lead to session theft.
  - The early returns also skip the optional passphrase encryption (`$doEncryption`). A user who asked for an encrypted download in the original-file branch gets plaintext.
  - The early return may also skip the download log entry. I could not confirm this from the diff. If the log call comes after these points, access to PHI goes unaudited.
- **Severity:** High
- **Fix:** Do not expose internal options as action parameters. Move the logic into a separate method, for example `get_document_contents($patient_id, $document_id)`, that is not callable as `*_action`. If a flag must stay, ignore it for web requests. Whichever route is used, always send `Content-Type` from a server-side allowlist, `Content-Disposition: attachment` and `X-Content-Type-Options: nosniff`, and write the audit log before returning.

### 2. Unvalidated `fopen` / `fread(filesize())` of `$url` (modified code)
- **Location:** the new `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));` in the original-file branch.
- **OWASP:** A01 Broken Access Control / A03 (path traversal), A10 SSRF-like.
- **Problem:**
  - The read is now unconditional. It happens even for plain downloads that previously streamed the file, so a whole file is loaded into memory. Large documents can exhaust memory (DoS).
  - The return value of `fopen` is not checked, and the handle is never closed.
  - `fread` with a length of 0 (an empty file) raises warnings.
  - `$url` comes from the database record. If an attacker can influence a document's `url` through upload, import or another injection, `fopen` accepts wrappers (`file://`, `http://`, `php://`). That gives local file read or SSRF. The diff does not show any check that `$url` stays inside the documents directory.
- **Severity:** Medium
- **Fix:** Resolve the path with `realpath()` and require it to be under `$GLOBALS['OE_SITE_DIR'].'/documents'`. Reject URL wrappers, check the `fopen` result, and use `readfile` or streaming instead of reading everything into memory.

### 3. Missing visible authorization and ownership checks (existing code this change relies on)
- **Location:** the top of `retrieve_action`, using `$patient_id` and `$document_id`.
- **OWASP:** A01 Broken Access Control.
- **Problem:** The visible code does not show an ACL check or confirm that `$document_id` belongs to `$patient_id`. If none exists elsewhere in the function, this is an IDOR that allows retrieval of any patient's documents by enumerating IDs. The new return-as-string path makes bulk harvesting through `$output` easier.
- **Severity:** High if confirmed. Please verify.

### 4. Other pre-existing issues in the touched function
- **Location:** `$_POST['encrypted']` and `$_POST['passphrase']`, and `"/encrypted_".$d->get_url_file()` in the temporary file path.
  - **OWASP:** A02 Cryptographic Failures, A05 Security Misconfiguration.
  - **Problem:** The passphrase is taken from the request body. The custom `encrypt()` implementation is unreviewed. The temporary encrypted file is written to a shared temp directory under a predictable name derived from the stored filename. The filename is not sanitized, which allows possible traversal or file collisions, and the temp file may not be reliably deleted.
  - **Severity:** Medium
- **Location:** `Controller::act()` and the `C_` class loader.
  - **OWASP:** A05 Security Misconfiguration.
  - **Problem:** The controller name and action are filtered to `[A-Za-z0-9_]`, so the loader is reasonably safe. But every public `*_action` method is externally invokable with arbitrary arguments, which is the root cause of finding 1. Error messages echo `$c_action` and `$name` unescaped. Those values are sanitized, so the risk is low, but it is still a bad pattern.
  - **Severity:** Low

### Summary
The main problem is that `disable_exit` can be set from the URL. It turns a download endpoint into one that serves uploaded content inline without safe headers (XSS), and it can bypass encryption and logging. Before merging, remove the parameter from the action signature and move the logic to a non-routable helper. Also confirm the authorization checks and harden the `fopen` path handling.