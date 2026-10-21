# Security Review: Controller.class.php

I've identified **one significant security vulnerability** and one design concern:

---

## 1. **Broken Access Control + Injection (String Interpolation in Error Messages)**
**Location:** Lines 171-173
```php
throw new NotFoundHttpException("Unable to load controller: $className");
```

**OWASP Category:** A01:2021 – Broken Access Control / A03:2021 – Injection

**Problem:** 
- `$className` is constructed from user input (`$controllerParam`) after whitelist lookup, but the error message uses direct string interpolation
- While the whitelist lookup itself is secure, if any whitelist entry could be manipulated or if the construction logic is future-modified, this could leak internal path information or be exploited for log injection attacks
- More critically, the pattern at line 179 (`new $className()`) uses dynamic class instantiation with a user-influenced name, creating a potential **variable variable vulnerability** if the whitelist is ever bypassed or extended unsafely

**Severity:** **Medium**

**Recommendation:**
```php
throw new NotFoundHttpException("Unable to load controller");
// Remove $className from error message to prevent information disclosure
```

---

## 2. **Insecure Design + Broken Access Control**
**Location:** Lines 119-140 (the entire `act()` method refactoring)

**OWASP Category:** A04:2021 – Insecure Design / A01:2021 – Broken Access Control

**Problem:**
- The legacy `act()` method now delegates to `dispatch()`, but the mapping between old positional parameters and new explicit parameters introduces ambiguity
- Line 130-136 renames the `action` parameter to `sub_action` to "avoid collision," but this is **implicit magic behavior** that's difficult to audit
- The comment suggests this is for "sub-controller delegation patterns" but there's no validation or documentation ensuring that sub-actions still undergo proper ACL checks
- Controllers not in `CONTROLLER_ACL_MAP` bypass ACL entirely (line 115-116), which may be intentional but represents a significant attack surface that should be explicitly documented

**Severity:** **Medium**

**Recommendation:**
1. Add explicit documentation about which controllers are ACL-protected and which are not
2. Consider a deny-by-default approach: require explicit ACL exemption rather than implicit allowance
3. Add logging for all ACL checks (see issue #3)

---

## 3. **Security Logging and Monitoring Failures**
**Location:** Lines 119-122 (ACL checks)

**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures

**Problem:**
- ACL check failures call `AccessDeniedHelper::denyWithTemplate()`, but there's no indication whether this method logs the failure
- The code doesn't log **successful** ACL checks either, making it difficult to audit who accessed what
- No logging of invalid controller/action requests (lines 157, 182-183)

**Severity:** **Low**

**Recommendation:**
```php
// Add explicit logging at ACL check points
private function checkControllerAcl(string $controllerName): void
{
    if (!isset(self::CONTROLLER_ACL_MAP[$controllerName])) {
        return; // Log this as "ACL not required" if needed
    }
    [$section, $value, $displayName] = self::CONTROLLER_ACL_MAP[$controllerName];
    if (!AclMain::aclCheckCore($section, $value)) {
        error_log("ACL DENIED: {$section}/{$value} for user: " . $_SERVER['REMOTE_ADDR']);
        // ...existing code
    }
}
```

---

## Summary

| Issue | Category | Severity |
|-------|----------|----------|
| String interpolation in error messages + dynamic class instantiation | Injection/Broken Access Control | Medium |
| Implicit sub_action renaming and inconsistent ACL application | Insecure Design | Medium |
| No logging of ACL checks or invalid requests | Logging Failures | Low |

The whitelist-based controller lookup (lines 24-33) is a **positive security improvement** over the regex-based approach in the original code. The refactoring generally improves security by making routing explicit, but the issues above should be addressed before merging.