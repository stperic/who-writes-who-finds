## Review: `interface/billing/get_claim_file.php`

This diff adds an authorization check to a billing file endpoint. It is a net security improvement, since it closes a broken access control gap. I found no blocking vulnerabilities in the changed lines, but I have a few items to verify and some minor observations.

### Findings

**1. Verify that `AccessDeniedHelper::denyWithTemplate()` terminates execution**
- **Location:** Lines added after `require_once`, the `if (!AclMain::aclCheckCore(...))` block
- **OWASP category:** A01:2021 Broken Access Control
- **Problem:** The security of this check depends on `denyWithTemplate()` calling `exit`/`die`. If it only renders a template and returns, the script continues to `verifyCsrfToken()` and the file-serving code, and the ACL check is bypassed for unauthorized users. The diff does not show the helper's implementation. Add an explicit `exit;` after the call as defense in depth, or confirm the helper always terminates.
- **Severity:** Medium if the helper does not exit (critical in that case, since it fully bypasses the control); informational otherwise.

**2. Write-level ACL for what appears to be a read/download operation**
- **Location:** `AclMain::aclCheckCore('acct', 'eob', '', 'write')` and `'bill', '', 'write'`
- **OWASP category:** A01:2021 Broken Access Control (least privilege)
- **Problem:** Downloading a claim file is a read operation, but the check requires `write`. This is not a vulnerability; it is stricter than a read check and may block legitimate read-only billing users. Confirm that this is the intended permission. If read access should suffice, use `'read'`.
- **Severity:** Low / informational (functional and policy correctness).

**3. Internal ACL names disclosed in the denial message**
- **Location:** `denyWithTemplate("ACL check failed for acct/eob or acct/bill: Billing Manager", ...)`
- **OWASP category:** A05:2021 Security Misconfiguration (information exposure)
- **Problem:** The first argument may be shown to the user or written to logs. It reveals internal ACL section names and the permission structure to any authenticated user who hits the endpoint. Use a generic message for the user and log the detail server-side.
- **Severity:** Low.

**4. Authorization is evaluated before the rest of the request is validated**
- **Location:** ACL check placed before `CsrfUtils::verifyCsrfToken($_GET["csrf_token_form"])`
- **OWASP category:** A04:2021 Insecure Design (ordering is acceptable here)
- **Problem:** The ordering is reasonable: authorization runs first and no state is changed. No action needed, but it is worth confirming that the rest of the file does not read request parameters or touch files before this point.
- **Severity:** Informational.

**5. CSRF token passed in the query string (pre-existing, not changed by this diff)**
- **Location:** `$_GET["csrf_token_form"]`
- **OWASP category:** A02:2021 Cryptographic Failures / A07:2021 Identification and Authentication Failures (token exposure)
- **Problem:** Tokens in URLs can leak through web server logs, browser history, and `Referer` headers. For a download endpoint this is a minor concern, but it is outside this diff.
- **Severity:** Low (pre-existing).

**6. Unreviewed code paths**
- **Location:** The remainder of `get_claim_file.php` (not included in the diff)
- **OWASP category:** A01:2021 / A03:2021 Injection
- **Problem:** Because this is a file-serving endpoint, the rest of the file should be checked for path traversal (for example, a filename or claim ID taken from `$_GET` and used in a filesystem path), for proper `Content-Type`/`Content-Disposition` handling, and for claim-level (not just module-level) authorization. The ACL added here is module-wide, so any user with billing write access can retrieve any claim file.
- **Severity:** Unknown; needs review of the full file.

### Summary

| # | Issue | Category | Severity |
|---|-------|----------|----------|
| 1 | Confirm `denyWithTemplate()` exits | A01 | Medium if not, else info |
| 2 | Write vs. read permission for download | A01 | Low / info |
| 3 | ACL names leaked in denial message | A05 | Low |
| 4 | Check ordering | A04 | Info |
| 5 | CSRF token in query string (pre-existing) | A07 | Low |
| 6 | Path handling and per-claim authz not visible | A01/A03 | Unknown |

**Recommendation:** Approve the change once item 1 is confirmed. Consider items 2 and 3 as follow-ups. Review the rest of the file for item 6 before merging, since the diff alone cannot show whether the file-serving logic is safe.