# Security Review: `C_Document::retrieve_action` (adds `$disable_exit`)

## Summary

The change adds a `$disable_exit` parameter that makes `retrieve_action` return file contents instead of sending them with headers and calling `exit`/`die`. The parameter is reachable from HTTP requests, the new code path skips the response headers, and the change adds an unclosed file handle. I'd block the merge until the first two findings are resolved.

## Findings

### 1. Request-controllable `$disable_exit` exposes raw file content with no safe content type (High)

- **Location:** `controllers/C_Document.class.php`, `retrieve_action()` signature and the new `if($disable_exit == true) { return ...; }` branches (three places); the dispatch in `library/classes/Controller.class.php`, `act()`.
- **OWASP category:** A01:2021 Broken Access Control; A03:2021 Injection (XSS as the consequence); A04:2021 Insecure Design.
- **Problem:** `Controller::act()` builds `$args_array` from URL query parameters and passes them positionally or by name to `*_action()`. Any query key that matches the method's parameter list is therefore attacker-controlled. A request such as `controller.php?document&retrieve&patient_id=…&document_id=…&disable_exit=1` sets `$disable_exit` to a truthy value. In the three new branches, `retrieve_action` then returns the document bytes to `act()`, which returns them to the front controller's `echo`. Several problems follow:
  - The `exit`/`die` that normally ends the response is skipped, so the response is whatever the action returns.
  - The response headers (`Content-Description`, `Content-Transfer-Encoding`, `Expires`, `Cache-Control`, `Pragma`) are not sent on this path. The diff shows no `Content-Type` or `Content-Disposition` header on any path, so the response defaults to `text/html`.
  - An uploaded `.html`, `.svg`, or `.js`-bearing document is returned as `text/html` from the application's own origin. That produces stored XSS against authenticated OpenEMR users.
  - The flag is a loose `== true` comparison, so any non-empty string other than `"0"` enables it.
- **Recommendation:** Do not expose internal control flags through the public argument path. Remove `$disable_exit` from the action signature and use a non-request mechanism, such as a separate internal method that both paths call, or a property set only by trusted server code. Make `act()` reject parameters that are not intended as request inputs. Also, `retrieve_action` should set `Content-Type` (for example `application/octet-stream`), `Content-Disposition: attachment`, and `X-Content-Type-Options: nosniff` on every return path, and should not return raw content through the HTML response.

### 2. Unclosed file handle and no error check on `fopen` (Low; reliability and minor DoS)

- **Location:** `controllers/C_Document.class.php`, the added `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));` block.
- **OWASP category:** A04:2021 Insecure Design; A05:2021 Security Misconfiguration (error handling).
- **Problem:** The handle `$f` is opened before the `disable_exit` check and is never closed on the early-return path. The result of `fopen` is not checked, so a missing or unreadable file produces a warning and `fread(false, …)`. The `filesize($url)` call is also made without a check. The whole file is read into memory even when the caller only wants a response that may be aborted.
- **Recommendation:** Check that `fopen` succeeded, call `fclose($f)` on every path, and move the read to after the flag check or into the branch that needs it. Use `readfile()` or a streamed copy for large documents.

### 3. Original `fopen` moved before authorization/logging checks (Low; needs confirmation)

- **Location:** Same block as finding 2.
- **OWASP category:** A09:2021 Security Logging and Monitoring Failures (potential).
- **Problem:** The diff moves the file read earlier in the function. The surrounding code, which is not shown, presumably performs access checks and calls `document_upload_download_log()` before or after serving. If the new early return skips a logging call that followed the header block, downloads made through the `disable_exit` path would be unlogged. I cannot confirm this from the diff.
- **Recommendation:** Verify that the ACL check and audit logging run before any file read or return, on every path.

## Pre-existing issues in code this change touches or relies on

These were not introduced by the diff but sit in the same request path.

### 4. Unescaped query string assigned to templates (Medium; possible reflected XSS)

- **Location:** `library/classes/Controller.class.php`, constructor: `$this->assign("CONTROLLER_THIS", "controller.php?" . $_SERVER['QUERY_STRING']);`, and `_link()`, which concatenates `$_SERVER['REQUEST_URI']` without encoding.
- **OWASP category:** A03:2021 Injection (XSS).
- **Problem:** The raw query string is placed into template variables. If a template prints it without escaping, an attacker can craft a link that injects script. I have not seen the templates, so this is a risk to verify, not a confirmed bug.
- **Recommendation:** Escape with `htmlspecialchars` at output, or URL-encode the value where it is built, and confirm that every template that uses `CONTROLLER_THIS` escapes it.

### 5. Dynamic controller loading and parameter injection from the URL (Medium)

- **Location:** `library/classes/Controller.class.php`, `act()`.
- **OWASP category:** A01:2021 Broken Access Control; A04:2021 Insecure Design.
- **Problem:** `act()` derives the controller and action names from the URL, sanitizes them with a character whitelist, and loads `C_<name>.class.php`. It then calls `*_action` with every remaining URL key as an argument. This is the mechanism that makes finding 1 possible. Any public action can receive any URL key that matches its parameter names, including future internal flags. The `@` suppression on `call_user_func_array(array(Controller,"i_once"), …)` also hides load failures.
- **Recommendation:** Map only an explicit allow-list of request parameters per action, and do not pass unrecognized keys to methods.

### 6. Unverified dependencies in this path

- **Location:** `retrieve_action()` relies on `$this->encrypt()`, `$d->get_url_file()`, `$GLOBALS['OE_SITE_DIR']`, and the ACL check at the top of the function. None of these are in the diff.
- **OWASP category:** A02:2021 Cryptographic Failures (for `encrypt`); A01:2021 (for the ACL check).
- **Problem:** The passphrase comes from `$_POST`, and the encryption scheme is not visible. I could not confirm the cipher, key derivation, or whether the ACL check runs before the new early returns.
- **Recommendation:** Review `encrypt()` for a modern authenticated cipher (for example AES-256-GCM) with a proper KDF (such as PBKDF2, scrypt, or Argon2). Confirm the ACL check precedes all returns in this function.

## Verdict

**Changes requested.** Finding 1 is a real exposure: the new flag is reachable from the URL and can cause a raw document to be returned as `text/html` from the application origin. Findings 2 and 3 should be fixed in the same change. Findings 4 through 6 are pre-existing and should be tracked separately.