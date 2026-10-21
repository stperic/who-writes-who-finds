# Security Review of Controller.class.php Pull Request

## Summary
This PR refactors the routing logic with improved security controls, but contains several security issues that require attention.

---

## Issues Found

### 1. **Broken Access Control (OWASP A01:2021)**
**Location:** Lines 169-171 (new `dispatch()` method)
**Problem:** The whitelist `VALID_CONTROLLERS` is incomplete and doesn't include all controllers that may be callable. An attacker could potentially bypass routing by directly instantiating controllers not in the whitelist through other means, or the whitelist may not cover all legitimate use cases as the system evolves.
**Severity:** HIGH
**Recommendation:** Document all controllers that should be routable. Consider using a registry or configuration file for controller registration rather than a hardcoded array. Add logging when controllers outside the whitelist are attempted.

---

### 2. **Broken Access Control (OWASP A01:2021)**
**Location:** Lines 160-166 (new `checkControllerAcl()` method)
**Problem:** The `CONTROLLER_ACL_MAP` only covers 2 controllers (`practice_settings` and `prescription`). Other controllers in `VALID_CONTROLLERS` bypass ACL checks entirely. This violates the principle of "secure by default" and could allow unauthorized access to controllers like `document`, `pharmacy`, etc.
**Severity:** HIGH
**Recommendation:** Either:
  - Add ACL mappings for ALL controllers in `VALID_CONTROLLERS`
  - Change the default behavior: deny access unless explicitly allowed
  - Document which controllers intentionally have no ACL requirements

---

### 3. **Injection Vulnerability (OWASP A03:2021) - Dynamic Method Invocation**
**Location:** Lines 196-198 (dynamic `$actionMethod` and `$processMethod` construction)
**Problem:** Although the action name is extracted from parameters, there's insufficient sanitization. The code uses:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
```
If `$action` contains special characters or method names, it could invoke unintended methods. The old code used `preg_replace("/[^A-Za-z0-9_]/", "", ...)` for sanitization, which is now missing.
**Severity:** MEDIUM
**Recommendation:** Add explicit sanitization:
```php
$action = preg_replace("/[^A-Za-z0-9_]/", "", $action);
if (empty($action)) {
    $action = 'default';
}
```

---

### 4. **Injection Vulnerability (OWASP A03:2021) - Parameter Keys**
**Location:** Lines 207-213
**Problem:** In the `act()` method, parameter keys from `$qarray` are used without sanitization in lines 138-139:
```php
foreach ($qarray as $key => $value) {
    if ($key === $controller || $key === $positionalAction) {
        continue;
    }
    $params[$key === 'action' ? 'sub_action' : $key] = $value;
}
```
An attacker could pass arbitrary parameter keys that might override critical parameters or trigger unintended behavior in controllers.
**Severity:** MEDIUM
**Recommendation:** Validate/whitelist allowed parameter names or sanitize keys similar to the original code.

---

### 5. **Security Misconfiguration (OWASP A05:2021)**
**Location:** Lines 180-185 (error handling)
**Problem:** While using exceptions is better than the old `echo` and `exit`, the error messages in `BadRequestHttpException` and `NotFoundHttpException` could leak information about controller structure to attackers:
```php
throw new BadRequestHttpException("Missing or invalid 'controller' parameter");
throw new NotFoundHttpException("Unable to load controller: $className");
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```
Attackers can enumerate valid controller names and actions through error responses.
**Severity:** MEDIUM
**Recommendation:** Use generic error messages in user-facing responses and log detailed errors server-side:
```php
throw new BadRequestHttpException("Invalid request");
// Log: error_log("Controller not found: $className");
```

---

### 6. **Security Logging and Monitoring Failures (OWASP A09:2021)**
**Location:** Lines 160-166 (ACL check implementation)
**Problem:** Failed ACL checks are delegated to `AccessDeniedHelper::denyWithTemplate()`, but there's no logging of:
  - Which user attempted to access which controller
  - Timestamp of the attempt
  - Success/failure of ACL checks
  
This makes it difficult to detect authorization bypass attempts or anomalous behavior.
**Severity:** MEDIUM
**Recommendation:** Add logging before calling `denyWithTemplate()`:
```php
error_log("ACL Check Failed - User: {$_SESSION['user']}, Controller: $controllerName, Required: $section/$value");
```

---

### 7. **Type Safety Issue (Not OWASP but Security-Adjacent)**
**Location:** Line 194
**Problem:** 
```php
$actionMethod = "{$action}_action";
$processMethod = "{$actionMethod}_process";
```
The method names are strings constructed without validation that the methods actually exist (beyond `is_callable()` check on line 204). Combined with issue #3, this creates risk.
**Severity:** LOW
**Recommendation:** Combine sanitization of `$action` with explicit existence checks before attempting to call.

---

### 8. **Existing Legacy Issue (Pre-existing in old code)**
**Location:** The old `act()` method (lines 78-101 in original)
**Problem:** The original code uses `array_reverse()`, `array_pop()`, and positional array parsing, making URL parameter order-dependent. While the new code improves this, it's worth noting this was a design vulnerability.
**Severity:** Previously MEDIUM (now addressed by new design)

---

## Security Improvements in This PR ✓
- Whitelist-based controller validation (replaces open regex replacement)
- Introduction of `BadRequestHttpException` and `NotFoundHttpException` (better than `exit`)
- Separation of concerns with `checkControllerAcl()`
- Order-independent routing via explicit parameters

---

## Recommendations Summary

| Priority | Issue | Fix |
|----------|-------|-----|
| **CRITICAL** | Incomplete ACL mappings | Add ACL requirements for all controllers or deny by default |
| **HIGH** | Incomplete whitelist validation | Document controller coverage and intent |
| **MEDIUM** | Missing action sanitization | Add `preg_replace("/[^A-Za-z0-9_]/", "", $action)` |
| **MEDIUM** | Parameter key injection | Sanitize or whitelist `$qarray` keys |
| **MEDIUM** | Information leakage in errors | Use generic error messages, log details server-side |
| **MEDIUM** | Missing audit logging | Log ACL failures with user context |