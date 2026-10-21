## Review Comments

**File:** `interface/billing/get_claim_file.php`

### 1. Unverified control-flow termination after ACL denial — *High/Critical*
```php
if (!AclMain::aclCheckCore(...) && !AclMain::aclCheckCore(...)) {
    AccessDeniedHelper::denyWithTemplate(...);
}
```
The code assumes `AccessDeniedHelper::denyWithTemplate()` halts execution (e.g., calls `exit`/`die` internally). If it merely renders a template/message and returns, execution will fall through to the CSRF check and then to the rest of the script, effectively **bypassing the ACL check** and still serving the claim file. This is a critical security assumption that should be explicit — add a defensive `exit;` immediately after the call, regardless of what the helper does internally, to guarantee the access-denied path cannot be bypassed.

### 2. Information disclosure in denial message — *Low*
```php
AccessDeniedHelper::denyWithTemplate("ACL check failed for acct/eob or acct/bill: Billing Manager", xl("Billing Manager"));
```
The first argument appears to be a log/debug message exposing internal ACL section/object names (`acct/eob`, `acct/bill`). If this string is rendered to the end user (not just logged), it leaks internal authorization structure to unauthorized users, which is minor but unnecessary information disclosure. Verify that this string is only used for server-side logging and never echoed back in the HTTP response.

### 3. Permission level may be too strict (`write` instead of `read`) — *Medium*
Fetching/downloading a claim file is typically a read operation, yet the check requires `write` access to either `acct/eob` or `acct/bill`:
```php
AclMain::aclCheckCore('acct', 'eob', '', 'write')
AclMain::aclCheckCore('acct', 'bill', '', 'write')
```
If other parts of the Billing Manager UI allow viewing/downloading claim files with only read-level billing permissions, this change could introduce a **functional regression**, denying legitimate read-only billing users access to a file they could previously retrieve. Confirm this matches the intended permission model elsewhere in the billing module (e.g., compare with how `aclCheckCore` is used for similar "view" endpoints).

### 4. Ordering of ACL vs. CSRF checks — *Low (style/defense-in-depth)*
The ACL check now runs before the CSRF token check. This is generally fine (authorization before request validation), but worth confirming intentional: an attacker without proper ACL rights will see the access-denied template rather than a generic CSRF failure, which is slightly more informative but not a significant issue. No action required, just a note for consistency with other endpoints in the codebase.

### 5. Pre-existing issue (not introduced by this diff) — *Informational*
The rest of the file (not shown in diff) presumably uses `$_GET` parameters to construct a file path for retrieval. This PR only adds ACL enforcement but does not address whether path/filename parameters are properly validated/sanitized against path traversal — worth double-checking as part of this review since the endpoint deals with file retrieval, a classic LFI/path-traversal vector. This isn't part of the diff, but since the PR touches this file's security posture, it's worth flagging for completeness.

---

### Summary
- **High:** Confirm `denyWithTemplate()` terminates execution; add explicit `exit` for defense in depth.
- **Medium:** Verify `write` ACL requirement doesn't break read-only billing users' ability to fetch claim files.
- **Low:** Avoid exposing internal ACL details in any user-facing denial message.
- **Informational:** Revisit file-path handling in the rest of the script for traversal risks, given this is a file-serving endpoint.