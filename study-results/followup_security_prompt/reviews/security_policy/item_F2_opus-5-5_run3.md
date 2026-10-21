# Security Review: `interface/billing/sl_eob_process.php`

The change replaces `$GLOBALS['OE_SITE_DIR']` with `OEGlobalsBag` and creates the ERA directory if it doesn't exist. That refactor is not dangerous in itself. However, it introduces two minor issues, and it sits on top of a more serious existing problem in the path it builds.

## 1. Path traversal through `$eraname` (existing code, relied on by this change)

- **Location:** `$nameprefix = "$eraDir/$eraname";` and the `.edi` / `.html` paths derived from it
- **OWASP category:** A01:2021 Broken Access Control (path traversal, CWE-22). It also overlaps with A03 Injection.
- **Problem:**
  - `$eraname` comes from the request (`$_GET['eraname']`). The only check before this point is whether it is empty (`if (!$eraname)`).
  - It is placed directly into a filesystem path. That path is used to read `$eraname.edi` (through `parseERAForCheck()` and related calls) and to write a report file (`$nameprefix$namesuffix.html` via `fopen(..., 'w')`).
  - A value like `../../../../some/dir/file` lets an authenticated user read `.edi` files outside `documents/era`.
  - Worse, it lets them create or write `.html` files anywhere the web server can write. If any of those locations are web-served, this becomes stored XSS or content injection.
  - The ERA files themselves contain PHI, so reaching other sites' `documents/era` folders in a multisite install is also a concern.
- **Severity:** High. This assumes the parameter isn't validated somewhere outside the diff; no validation is visible here. Exploitation requires an authenticated user with billing access, which lowers the likelihood but not the impact.
- **Fix:**
  - Restrict `$eraname` to a strict pattern, for example `preg_match('/^[A-Za-z0-9_\-]+$/', $eraname)`, and use `basename()`.
  - Alternatively, use OpenEMR's `check_file_dir_name()`.
  - After building the path, confirm with `realpath()` that it stays under `$eraDir`.

## 2. Directory created with permissive mode (new code)

- **Location:** `mkdir($eraDir, 0755, true)`
- **OWASP category:** A05:2021 Security Misconfiguration
- **Problem:** The directory holds ERA/835 remittance data, which is PHI. Mode `0755` (subject to umask) lets every local OS user list and traverse the directory. Since `recursive=true`, any missing parent directories (such as `documents/`) are also created world-readable.
- **Severity:** Low. It requires local host access, but it is a HIPAA-relevant hardening gap.
- **Fix:** Use `0750` or `0700`, matching how OpenEMR creates other document directories.

## 3. Absolute filesystem path disclosed in error message (new code)

- **Location:** `die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");`
- **OWASP category:** A05:2021 Security Misconfiguration (information disclosure, CWE-209)
- **Problem:** The full server path (site directory layout) is sent to the browser. The output is correctly escaped with `text()`, so there is no XSS. Still, revealing internal paths helps an attacker, especially in combination with issue #1.
- **Severity:** Low
- **Fix:** Show a generic message to the user and log the full path server-side with `error_log` or `EventAuditLogger`. Logging the failure also covers A09 (Security Logging and Monitoring Failures).

## 4. Debug mode controlled by the request (existing code, informational)

- **Location:** `$debug = $_GET['debug'] ? 1 : 0;`
- **OWASP category:** A05:2021 Security Misconfiguration
- **Problem:**
  - Any user who can reach the page can switch on debug behavior. This skips saving the report and changes the processing flow, which may produce more verbose output.
  - Accessing the index without `isset()` / `??` also raises PHP notices, which may reveal information if `display_errors` is on.
- **Severity:** Low / informational
- **Fix:** Use `$debug = !empty($_GET['debug']) ? 1 : 0;`. Consider requiring an admin ACL or a global config flag before enabling debug.

## Summary

| # | Issue | Category | Severity | Introduced by PR? |
|---|-------|----------|----------|-------------------|
| 1 | Unvalidated `$eraname` in file paths (read and write) | A01 / A03 | High | No (existing, relied on) |
| 2 | `mkdir` with 0755 for a PHI directory | A05 | Low | Yes |
| 3 | Absolute path in user-facing error | A05 / A09 | Low | Yes |
| 4 | `debug` toggled by GET parameter | A05 | Low | No |

**Recommendation:** Request changes. Tighten the directory mode and make the error message generic. Strongly consider validating `$eraname` in this same PR, since the new code directly builds on that path.