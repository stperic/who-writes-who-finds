# Security Review: `interface/billing/sl_eob_process.php`

## Summary

The change itself is small and mostly safe. It moves to `OEGlobalsBag`, creates the ERA directory if it is missing, and HTML-escapes the error output. However, the new code builds file paths from `$eraname`. That variable is request-controlled and does not appear to be validated, which is a pre-existing problem the change relies on. There are also two low-severity issues in the new lines.

---

## Findings

### 1. Path traversal via `$eraname` (existing code that the change relies on)
- **Location:** `$nameprefix = "$eraDir/$eraname";`, `$eraFilePath = $nameprefix . '.edi';`, and the later read/write of `"$nameprefix.html"` (the saved report).
- **OWASP category:** A01:2021 Broken Access Control (path traversal). The resulting file write is also related to A03 Injection.
- **Problem:** In this script, `$eraname` comes from the request (`$_GET['eraname']`). The visible code only checks that it is non-empty (`if (!$eraname)`). Nothing in the diff strips `../`, slashes, or null bytes before it is joined into a filesystem path. An authenticated user could pass something like `eraname=../../../../some/path/x`, which would let them:
  - **Read** any `*.edi` file the web server can reach, through `parseERAForCheck()` and the ERA processing.
  - **Write** the generated HTML report (`x.html`) to an arbitrary writable location. That location could be inside the web root, leading to stored XSS or content injection under the application's origin.
- **Severity:** **High** if `$eraname` is not sanitized earlier in the file (outside the diff context). The access-control check limits this to authenticated users with billing/EOB permissions, but those users should still not be able to escape `documents/era`.
- **Recommendation:**
  ```php
  $eraname = $_GET['eraname'] ?? '';
  if (!preg_match('/^[A-Za-z0-9_.\-]+$/', $eraname) || str_contains($eraname, '..')) {
      die(xlt("Invalid ERA name"));
  }
  ```
  - Alternatively, use `basename()` on the value.
  - Also verify that `realpath(dirname($eraFilePath)) === realpath($eraDir)` before reading or writing.

### 2. Full filesystem path disclosed in error message (new code)
- **Location:** `die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");`
- **OWASP category:** A05:2021 Security Misconfiguration (information disclosure).
- **Problem:** The absolute server path (`OE_SITE_DIR/documents/era`) is shown to the user. The output is correctly escaped with `text()`, so there is no XSS. Still, it reveals the installation layout and site directory name, which can help an attacker with other exploits.
- **Severity:** **Low**
- **Recommendation:** Log the full path with `error_log()` or `EventAuditLogger`, and show the user a generic message.

### 3. Permissive directory mode for PHI storage (new code)
- **Location:** `mkdir($eraDir, 0755, true)`
- **OWASP category:** A05:2021 Security Misconfiguration (and A02 Cryptographic Failures / data protection, in spirit).
- **Problem:** ERA/835 files and the generated reports contain PHI: patient names, claim and payment data. Mode `0755` with `recursive=true` makes the directory, and any parent directories it creates, world-readable and traversable for other local users on the host.
- **Severity:** **Low** (requires local access; also depends on the umask and hosting model).
- **Recommendation:** Use `0750` or `0700`, which matches how OpenEMR's documents directories are expected to be protected. Also confirm that `documents/` is not web-served (for example, via an `.htaccess`/nginx deny rule).

### 4. Debug mode toggled by any user via GET (existing code)
- **Location:** `$debug = $_GET['debug'] ? 1 : 0;`
- **OWASP category:** A05:2021 Security Misconfiguration / A04 Insecure Design.
- **Problem:** Any user who can reach the page can switch to debug mode. In this script that means a dry run with extra diagnostic output. It is low risk, but debug behavior should not be controlled by the client in production. The code also reads `$_GET['debug']` without `isset`, which raises notices.
- **Severity:** **Informational / Low**
- **Recommendation:** Restrict debug mode to a configuration flag or an admin ACL, and use `!empty($_GET['debug'])`.

---

## Things checked and found acceptable in the diff
- **XSS in the new error message:** the output is wrapped in `xlt()` and `text()`, so it is properly escaped.
- **Directory creation race:** the `!is_dir() && !mkdir() && !is_dir()` pattern correctly handles a concurrent create.
- **CSRF and ACL:** these are not changed by this diff. Confirm that the existing `CsrfUtils::verifyCsrfToken()` and `AclMain::aclCheckCore('acct', 'eob')` checks still run before this code.

**Recommendation:** Before merging, add validation of `$eraname` (Finding 1) and tighten the directory permissions (Finding 3). These are small changes in the same block of code.