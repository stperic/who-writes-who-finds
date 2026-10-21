## Security Review – `sl_eob_process.php` diff

### 1. Path Traversal via unsanitized `$eraname` used to build filesystem paths
**Location:** 
```php
$nameprefix = "$eraDir/$eraname";
$eraFilePath = $nameprefix . '.edi';
```
**OWASP Category:** A03:2021 – Injection (Path Traversal) / A01:2021 – Broken Access Control

**Problem:** The diff changes *how* the base directory (`$eraDir`) is obtained (via `OEGlobalsBag` instead of `$GLOBALS`), but it does not add any validation to `$eraname` before it is concatenated into a filesystem path. If `$eraname` is derived from user-controllable input (query string, uploaded filename, form POST, etc. — as is typical for ERA/EOB processing), an attacker could supply a value containing `../` sequences or absolute paths to read or write files outside the intended `documents/era` directory. Since this write path is later used for `.edi` report files, this could lead to arbitrary file write/overwrite on the server.

This is a pre-existing weakness (it also existed in the old `$GLOBALS['OE_SITE_DIR']` line), but the new code still relies on `$eraname` unsanitized, so it should be fixed now: validate/whitelist `$eraname` (e.g., `basename()` + strict regex for allowed characters) before using it in a path.

**Severity:** High (if `$eraname` is attacker-influenced) — unresolved by this PR.

---

### 2. Information Disclosure in Error Message
**Location:**
```php
die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");
```
**OWASP Category:** A05:2021 – Security Misconfiguration (verbose error / information exposure)

**Problem:** On failure, the full server-side absolute path is echoed back to the client. While it is correctly HTML-encoded (`text()`), revealing internal directory structure to end users (especially unauthenticated or low-privileged ones, depending on access control elsewhere in the request flow) aids attackers in further reconnaissance/path-traversal attempts, and generally violates least-information-disclosure principles for error handling.

**Severity:** Low–Medium

---

### 3. Overly Permissive / Unverified Directory Creation for Sensitive Documents
**Location:**
```php
if (!is_dir($eraDir) && !mkdir($eraDir, 0755, true) && !is_dir($eraDir)) {
```
**OWASP Category:** A05:2021 – Security Misconfiguration

**Problem:** The newly created `documents/era` directory is created with mode `0755` (world-readable/executable). This directory stores ERA/EOB files, which typically contain PHI (patient billing/remittance data). Depending on the web server's document root configuration and OS-level multi-tenant setup, a world-readable directory increases risk of unauthorized local access. There is also no verification that this directory is outside the web-servable root or protected by a deny-all `.htaccess`/web server config (OpenEMR typically protects the `documents` directory via web server rules, but this isn't verified here, and the PR introduces new directory-creation logic that should explicitly enforce restrictive permissions, e.g., `0750` and ownership scoped to the web server user only).

**Severity:** Medium (elevated due to PHI/HIPAA sensitivity of ERA/EOB documents)

---

### 4. (Pre-existing, touched by this change) Reliance on `$eraname`/request data without visible authentication/authorization checks in this snippet
**Location:** Entire file context (not shown in diff, but relied upon)

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** The diff doesn't show access control checks around who can trigger ERA/EOB file processing and directory creation. If this endpoint is reachable without proper role/permission checks (e.g., only billing-admin ACL), combined with issue #1 (path traversal), this becomes a more severe arbitrary file write primitive. This should be verified in the surrounding code (not visible in diff) to ensure proper `acl_check()`/session validation precedes this logic.

**Severity:** Informational/Medium (dependent on surrounding code not shown)

---

## Summary
| # | Issue | OWASP Category | Severity |
|---|-------|----------------|----------|
| 1 | Path traversal via `$eraname` in file path construction | A03 Injection / A01 Broken Access Control | High |
| 2 | Server path disclosed in die() error message | A05 Security Misconfiguration | Low–Medium |
| 3 | New ERA directory created with permissive `0755` mode | A05 Security Misconfiguration | Medium |
| 4 | Unverified access control around file-path-influencing input | A01 Broken Access Control | Medium (needs confirmation) |

**Recommendation:** Sanitize/validate `$eraname` strictly (whitelist characters, `basename()`, reject `..`/path separators) before path concatenation, reduce new directory permissions to the minimum required (e.g., `0750`), and avoid echoing full server paths in user-facing error messages. Confirm this endpoint enforces proper authentication/authorization prior to performing file system writes.