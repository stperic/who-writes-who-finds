## Issues Found

**Location**: Lines 21-23  
**Problem**: Security check ordering — The ACL check runs before CSRF token verification. CSRF validation should typically occur before permission checks to prevent information disclosure about whether a user has access to a resource. An attacker could use timing differences or error messages to determine if a target user has billing permissions.  
**Severity**: Medium

**Location**: Line 22  
**Problem**: Information disclosure in error message. The first argument to `denyWithTemplate()` explicitly states which ACL permissions are being checked (`"ACL check failed for acct/eob or acct/bill"`). This reveals implementation details that could help an attacker understand the authorization structure. The message should not disclose what permissions are required.  
**Severity**: Low

---

**Recommendation**: Swap the ACL and CSRF checks so CSRF validation runs first:
```php
if (!CsrfUtils::verifyCsrfToken($_GET["csrf_token_form"])) {
    CsrfUtils::csrfNotVerified();
}

if (!AclMain::aclCheckCore('acct', 'eob', '', 'write') && !AclMain::aclCheckCore('acct', 'bill', '', 'write')) {
    AccessDeniedHelper::denyWithTemplate("Access denied", xl("Billing Manager"));
}
```

Also consider removing the ACL details from the first error message parameter.
