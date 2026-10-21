# Review: `interface/billing/get_claim_file.php`

The diff adds an ACL check before the CSRF check. That is the right direction. The endpoint previously relied on CSRF alone, so any authenticated user could download claim files, which contain PHI. Below are issues in the change and in the code it protects. The diff shows only the header of the file, so findings about the file body are based on how this endpoint works upstream and should be confirmed against the full file.

## 1. Path traversal in the file name parameter (pre-existing, High)

**Location:** the file body after the CSRF check, where `$_GET['key']` (and possibly a partner or format parameter) is used to build a path under `$GLOBALS['OE_SITE_DIR'] . "/documents/edi/"`.

**Problem:**
- This endpoint has a history of path traversal problems.
- Older versions sanitized the name with ad-hoc `preg_replace` calls that strip `/`, `..` and `\`. That approach is fragile.
  - Single-pass removal can be bypassed. For example, `....//` becomes `../` after one pass of removing `..` and `/`.
  - It does not handle encodings or absolute paths consistently.
- The new ACL check narrows who can reach this code to billing users. It does not remove the risk: a billing user, or anyone who hijacks a billing session, could read arbitrary files the web server can access, such as `sites/*/sqlconf.php` or other patients' documents.

**Recommendation:**
- Validate the name with `check_file_dir_name()`, or use `basename()` plus a strict allow-list regex such as `^[A-Za-z0-9._-]+$`.
- Resolve the path with `realpath()` and confirm it still starts with the EDI directory before calling `readfile()`.

## 2. Unsanitized file name in `Content-Disposition` (pre-existing, Low–Medium)

**Location:** the download headers in the file body.

**Problem:** If the user-supplied name is echoed into `Content-Disposition: attachment; filename=...` without quoting or escaping, a crafted name can:
- break the header, or
- produce a misleading download name.

PHP blocks CR/LF injection in `header()`, but quotes and semicolons still get through.

**Recommendation:** Quote and sanitize the name, or use only the validated basename.

## 3. CSRF token read from `$_GET` without an existence check (Low)

**Location:** `CsrfUtils::verifyCsrfToken($_GET["csrf_token_form"])`

**Problem:**
- If the parameter is missing, PHP raises an undefined-index warning before the check fails. Use `$_GET['csrf_token_form'] ?? ''`.
- Passing the token in a GET query string also exposes it in server logs, browser history and `Referer` headers. This is acceptable for a download link, but worth knowing.

## 4. ACL semantics (Low, verify)

**Location:** the new `aclCheckCore` condition.

**Problem:**
- The check requires `write` on `acct/eob` or `acct/bill`.
- Downloading a claim file is a read operation, so users who legitimately view billing data with read-only access may now be locked out.
- Check that this matches the ACL used by the Billing Manager page that links here (`billing_report.php`). If the two differ, the UI will show a link the user cannot follow.
- Also confirm that `AccessDeniedHelper::denyWithTemplate` terminates execution (it calls `exit`). If it does not, the check offers no protection.

## 5. No audit logging of PHI download (Low, maintainability/compliance)

**Problem:** Claim files contain PHI, and nothing records who downloaded which file.

**Recommendation:** Add an `EventAuditLogger` entry for each download.

## Summary

The ACL addition is correct and worthwhile. The most important follow-up is to confirm, and if needed fix, path validation on the `key` parameter in the body of this file. Access control alone does not mitigate path traversal.