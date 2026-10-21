# Security Review - get_claim_file.php

## Summary
**One security issue found - Moderate severity**

---

## Issue #1: Broken Access Control - ACL Check Ordering

**Location:** Lines 21-23 (ACL check) and Line 25 (CSRF check)

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** The ACL (Access Control List) check is performed *before* the CSRF token verification. This creates a timing vulnerability where:
1. An attacker can probe whether a user has billing permissions by observing response differences
2. More critically, if an ACL check fails and denies access, the CSRF token is never validated, potentially leaking information about whether the token was valid
3. An attacker could craft requests and use the ACL denial response to infer whether a given CSRF token belongs to an authenticated user

**Severity:** Moderate

**Recommendation:** Reverse the order - verify the CSRF token *first*, before performing ACL checks. This follows the principle of validating request integrity before checking authorization:

```php
if (!CsrfUtils::verifyCsrfToken($_GET["csrf_token_form"])) {
    CsrfUtils::csrfNotVerified();
}

if (!AclMain::aclCheckCore('acct', 'eob', '', 'write') && !AclMain::aclCheckCore('acct', 'bill', '', 'write')) {
    AccessDeniedHelper::denyWithTemplate("ACL check failed for acct/eob or acct/bill: Billing Manager", xl("Billing Manager"));
}
```

---

## Positive Findings
- ✓ CSRF protection is implemented
- ✓ ACL checks are in place
- ✓ Uses parameterized/protected methods rather than direct query building