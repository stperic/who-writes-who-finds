## Summary

This change adds a `$disable_exit` flag to `C_Document::retrieve_action()` so the method can be called "internally" and return file bytes instead of streaming them to the browser with headers and then `exit`/`die`. The mechanism by which this method is invoked (`Controller::act()`) makes the new parameter directly reachable from untrusted HTTP requests, and the new code paths reintroduce several classes of risk. Findings below.

---

### 1. Newly‑reachable, unvalidated control parameter (`$disable_exit`)
**Location:** `controllers/C_Document.class.php`, `retrieve_action()` signature and all three new `if ($disable_exit == true) { … }` blocks.
**OWASP category:** A01:2021 – Broken Access Control / A04:2021 – Insecure Design

**Problem:** `retrieve_action()` is dispatched generically by `Controller::act()` (see `library/classes/Controller.class.php`), which builds the argument list straight from the request’s query-string keys/values and calls the action method with `call_user_func_array()`. Because the array passed is associative (keyed by parameter name taken from the query string), on PHP 8+ this is matched against the function’s **named parameters**. That means an external caller can simply add `disable_exit=1` (or any non-"0", non-empty string) to the URL to force this new code path — regardless of its intended "internal only" position as the 5th argument.

There is no capability check, no allow-list of which new parameters are safe to expose, and no documentation/guard preventing this. Any parameter added to an `*_action` method automatically becomes web-reachable. This turns what looks like an internal refactor into an externally triggerable behavior change.

**Severity:** High

---

### 2. Raw document content returned without headers/sanitization (potential stored XSS / content-type confusion)
**Location:**
```php
if($disable_exit == true) {
    return base64_decode($content);   // CouchDB branch
}
...
if($disable_exit == true) {
    return $filetext;                 // filesystem branch
}
```
**OWASP category:** A03:2021 – Injection (Cross-Site Scripting) / improper output handling

**Problem:** Normally the file is sent with explicit headers (`Content-Description`, `Content-Transfer-Encoding: binary`, etc.) and the process `die()`s, fully controlling how the browser treats the bytes. With `$disable_exit`, the raw document bytes are instead `return`ed from the action method, which (per `Controller::act()`) get concatenated into `$output` and ultimately echoed by the calling script. No `Content-Type`/`Content-Disposition` header is set, and no output encoding/escaping is performed.

If a patient document was ever uploaded as HTML/SVG/JS (or an attacker can get such a file accepted as a "document"), this path causes its content to be reflected directly into the page response, likely resulting in stored XSS when rendered by the browser (MIME sniffing will treat it as HTML in the absence of a `Content-Type` header). Even for benign binary files, dumping raw bytes without headers into an HTML response is a content-type confusion risk.

**Severity:** High

---

### 3. Unconditional full file read into memory / resource leak
**Location:**
```php
$f = fopen($url,"r");
$filetext = fread( $f, filesize($url) );
if($disable_exit == true) {
    return $filetext;
}
```
**OWASP category:** A04:2021 – Insecure Design (resource exhaustion) / minor misconfiguration

**Problem:** Previously, `fread()` of the entire file into memory only happened when `$doEncryption` was true. Now it happens unconditionally for every request that takes the `$original_file` path, even when the data will just be streamed or discarded. Combined with finding #1 (attacker can force `disable_exit=1`), this lets any user with access to this action force the server to load an arbitrarily large document fully into PHP memory on every call — a potential Denial-of-Service vector. The file handle `$f` is also never closed (`fclose` missing), leaking file descriptors over time.

**Severity:** Medium

---

### 4. Inconsistent/incomplete contract for `$disable_exit` in the "converted file" branch
**Location:**
```php
if($disable_exit == true) {
    return ;
}
```
**OWASP category:** A04:2021 – Insecure Design (reliability/correctness, indirectly a security concern)

**Problem:** In this branch the function silently returns `null` instead of the actual content, even though the caller asked for `disable_exit`. Inconsistent contracts like this tend to produce swallowed errors or incorrect assumptions by future callers (e.g., code that treats `null` as "empty file" and writes it somewhere, or fails to detect a bypassed retrieval). Not directly exploitable here, but it's the kind of logic flaw that leads to security-relevant bugs later.

**Severity:** Low

---

### 5. Pre-existing issues this change touches/relies on (not introduced here, but relevant)

- **`$_POST['encrypted']` / `$_POST['passphrase']` used directly for crypto operations** (same function, unchanged lines) — no validation of passphrase strength, no CSRF protection on an action that can write temp files (`$tmpfilepath . "/encrypted_" . ...`) to disk. OWASP: A02:2021 – Cryptographic Failures / A01:2021 Broken Access Control (CSRF). The new `$disable_exit` paths bypass this encryption logic entirely in the filesystem branch example (content returned *before* the `$doEncryption` block even runs), meaning when `disable_exit` is used, passphrase-protected/encrypted documents are returned in **plaintext**, defeating the encryption feature.
- **No audit logging on successful retrieval.** The failure path explicitly calls `$this->document_upload_download_log(...)` before `die()`, but the success path (including both new early-return branches) does not appear to log anything. OWASP: A09:2021 – Security Logging and Monitoring Failures. The new return paths make this gap worse because they are a second, less visible, way to exfiltrate document content with zero audit trail.
- **`Controller::act()` generic dispatch** (`library/classes/Controller.class.php`): building the method name and its argument list directly from attacker-controlled query-string keys with only a generic `[^A-Za-z0-9_]` character filter, then invoking via `call_user_func_array`, is itself an insecure design pattern (A04:2021) that is what makes finding #1 possible. Any future parameter added to any `*_action` method is implicitly exposed to the web with no allow-listing — this should be reviewed independently of this PR.
- **Unvalidated `$url`/file path construction** (code above the shown diff, not included): it cannot be confirmed from this diff whether `$url` is safely constrained to the documents directory or whether `$document_id`/patient path components are sanitized against path traversal. Since `fopen()` can also follow `http://`, `ftp://`, `php://` wrappers if `allow_url_fopen` is enabled, this is worth explicit verification — especially now that `$disable_exit` provides a direct way to get arbitrary file content returned as a string without ever touching the browser's download handling (increasing the impact of any such flaw, e.g., turning a path traversal into a one-shot read of arbitrary readable files or an SSRF primitive).

---

## Recommendations

1. Do not let request-dispatchable methods accept "trusted-only" flags like `$disable_exit` as ordinary parameters. Split this into a genuinely private/internal method (e.g. `_retrieve_contents()`), and keep `retrieve_action()` as the thin, web-facing wrapper that always performs the full header/exit flow.
2. If internal reuse is needed, explicitly strip/ignore any `disable_exit`-style keys found in `$_GET`/`$_POST` before dispatch, or change `Controller::act()` to use an explicit allow-list of parameter names per action instead of blindly forwarding all query keys.
3. When returning raw content for internal reuse, never let it reach the HTTP response unprocessed — the eventual caller must set appropriate `Content-Type`, `Content-Disposition: attachment`, and (if echoing in HTML context) properly encode/escape or refuse to render untrusted MIME types.
4. Keep the `fread()` conditional on `$doEncryption` (or otherwise only reading what is needed), close file handles, and consider streaming (`readfile()`/chunked output) for large files instead of loading them fully into memory.
5. Ensure successful retrievals are logged via `document_upload_download_log()` just like failures, and ensure the new return paths still invoke the same authorization/logging code as the normal path.
6. Verify (if not already true) that encryption still applies to content returned via `$disable_exit`, so plaintext isn't leaked for documents that are supposed to be passphrase protected.