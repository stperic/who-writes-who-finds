## Review: adding an ACL check to `get_claim_file.php`

The change adds an authorization check that was missing before, which is a good direction. I have a few concerns, and most depend on code outside the diff.

### Issues

**1. Permission level may be wrong (Medium)**
*Location:* the `if` at the top of the new block.
The check requires `'write'` on `acct/eob` or `acct/bill`. Serving a claim file for download is a read operation. Requiring write access would deny users who should be able to view claim files but not modify billing data. It would also be inconsistent with any page that reads the same files. Unless the file is only ever fetched in a write workflow, this should probably be `'read'`. Please confirm the intended level against the calling pages and the ACL definitions.

**2. Logic is OR-ed across two sections without justification (Low)**
*Location:* `aclCheckCore('acct','eob',...) && aclCheckCore('acct','bill',...)`.
The condition grants access if the user has either permission. That may be intentional, but the reason should be documented. If claim files are PHI, the broader grant should be confirmed with the security owners.

**3. Correctness depends on `denyWithTemplate()` terminating execution (High if false, otherwise none)**
*Location:* the `denyWithTemplate(...)` call.
The new code is only safe if `AccessDeniedHelper::denyWithTemplate()` calls `exit`/`die` (or otherwise halts). If it returns, the script continues to the CSRF check and then to the file-serving code, so the ACL check would not protect anything. Please verify this in the helper's implementation, or add an explicit `exit;` after the call so the behaviour does not depend on it.

**4. Unverified file-handling code (High, cannot assess from diff)**
*Location:* the rest of `get_claim_file.php`, which is not shown.
This script presumably takes a file identifier or path from `$_GET` and streams it back. The diff does not show how that input is validated. Please confirm that:
- the input is not used directly in a filesystem path (path traversal, e.g. `../`);
- the file is restricted to the intended claim-file directory;
- the response uses safe headers (`Content-Type`, `Content-Disposition`), and the filename is sanitized.

The ACL check gates who can call the script, but it does not stop a permitted user from requesting arbitrary files if the path handling is weak.

**5. Ordering and CSRF on a GET request (Low)**
*Location:* the CSRF check reads `$_GET["csrf_token_form"]`.
If the parameter is missing, this raises an undefined-index notice (pre-existing). Also, a CSRF token passed in a GET query string can leak through logs, referrers, and browser history. This is pre-existing, but it is worth noting while the file is being touched. The ACL check running before the CSRF check is acceptable.

**6. Denial message is hard-coded English and exposes internals (Low)**
*Location:* `denyWithTemplate("ACL check failed for acct/eob or acct/bill: Billing Manager", ...)`.
The first argument appears to be a log or internal message, and it names specific ACL sections. If it is displayed to the user, it reveals internal permission structure. It also differs from the translated `xl("Billing Manager")` title. Consider a plain message for the user and keep the detailed text in the log.

### Summary

The addition is a reasonable fix for a missing authorization check. Before merging, I would ask the author to:
- confirm `'write'` is the intended permission (probably should be `'read'`);
- confirm `denyWithTemplate()` exits, or add an explicit `exit;`;
- review the unchanged file-handling code for path traversal and header safety, since the ACL check alone does not fully secure the endpoint.