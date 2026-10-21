## Review of `interface/billing/get_claim_file.php`

### Issues in the added code
None. The change is a security improvement.

- **Broken access control (A01), fixed.** Before this change, any authenticated user who passed the CSRF check could download claim files. These files contain PHI and billing data. The new check requires `acct/eob` write or `acct/bill` write.
- **Logic:** `!A && !B` denies only when the user has neither permission, which is the intended "either role suffices" behavior.
- **Ordering:** the ACL check runs before the CSRF check and before any file handling, which is correct.
- **Information disclosure:** the detailed ACL string is for the server-side log. The user sees only the generic "Billing Manager" label.

### Things to verify (code the diff touches or relies on)
The diff doesn't show the rest of the file, so I can't confirm these. They are worth checking before merge.

1. **Path traversal / arbitrary file read (A01, possibly A03), severity High if present.**
   - The script serves a file based on a request parameter, typically `$_GET['filename']`, from the EDI directory.
   - Confirm the value is reduced with `basename()` or checked against an allowlist or `realpath()` prefix. Otherwise `../` sequences could expose other site files such as `sqlconf.php`.
   - Also confirm that `AccessDeniedHelper::denyWithTemplate` terminates execution with `exit`/`die`. If it returns, the file would still be served.

2. **CSRF token passed in the query string (A04/A02-adjacent), severity Low.**
   - `$_GET["csrf_token_form"]` puts the token in the URL, where it can leak through logs, browser history and Referer headers.
   - It is also read without an `isset` check, which can raise a notice or pass `null` to the verifier.
   - A POST request, or at least an `isset` guard, would be better. The download is state-changing in the sense that it may mark or move claim files.

3. **Response headers and filename handling (A05), severity Low.**
   - Confirm `Content-Disposition` uses the sanitized filename, with no CR/LF header injection.
   - Confirm a fixed content type is sent, such as `application/octet-stream` or `text/plain`.
   - Confirm `X-Content-Type-Options: nosniff` is set.

4. **Logging (A09), severity Low/Informational.**
   - Confirm successful claim-file downloads are audit-logged, for example with `EventAuditLogger`. PHI access should leave a trail.
   - Denied attempts are presumably logged by `AccessDeniedHelper`.

### Summary
The diff adds a missing authorization check correctly and introduces no new vulnerabilities. The main residual risk is path traversal in the unshown filename handling, which should be confirmed. The other items are lower-severity hardening.