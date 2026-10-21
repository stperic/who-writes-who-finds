## Review result: no new security issues found

This diff fixes a vulnerability rather than adding one.

### What the change does
`get_claim_file.php` serves generated claim files (X12/EDI), which contain PHI. Before this change it checked only the CSRF token and a logged-in session (via `globals.php`). Any authenticated user, including a low-privileged one, could download billing files if they had a valid token. The diff adds an ACL check that requires `acct/eob` write or `acct/bill` write. That closes a **Broken Access Control (A01:2021)** gap.

### Verification of the new check
- **Logic:** `!A && !B` denies only when the user has neither permission, so access is granted if either is held. This matches the intended "billing manager" semantics.
- **Fail-closed behavior:** The check runs before any file handling or output. This is only safe if `AccessDeniedHelper::denyWithTemplate()` terminates execution, as it does in OpenEMR (it is `never`-returning and exits). If it ever returned, the code would fall through and fail open, so confirm this.
- **Ordering:** Authorization before CSRF verification is fine. Neither check depends on the other.
- **Logging:** The denial message is a static string with no user input, so there is no log injection. Denials are recorded, which supports A09.

### Observations (not blocking, pre-existing or outside the diff)
| Location | Category | Note | Severity |
|---|---|---|---|
| `$_GET["csrf_token_form"]` (context line) | A05/A04 | There is no `isset` check, so a missing parameter raises a PHP notice or warning. `verifyCsrfToken` should still reject it, but this is worth hardening. A GET-based CSRF token can also leak through logs and Referer headers. | Low / informational |
| Remainder of the file (not in the diff) | A01/A03 | I couldn't see how the requested file name (e.g. `$_GET['key']`) is turned into a path. Confirm it uses `basename()` or an allowlist and is confined to the EDI directory, to rule out path traversal and arbitrary file read. | Needs verification |

### Recommendation
Approve. Optionally, add a test that a user without billing ACLs gets a denial, and check the file-path handling in the unchanged part of the script.