# Security Review: Controller.class.php Pull Request

## Summary
This PR refactors the routing logic in the Controller class from positional parameter parsing to explicit `controller` and `action` parameters, with a whitelist-based controller validation system. While the changes improve security in several ways, there are notable vulnerabilities remaining.

---

## Issues Found

### 1. **Broken Access Control (OWASP A01:2021)** - HIGH SEVERITY

**Location:** `C_PracticeSettings.class.php` constructor (lines 15-18)

**Problem:** 
The ACL check in `C_PracticeSettings::__construct()` duplicates the ACL check that now exists in `Controller::checkControllerAcl()`. However, the controller constructor is called *after* `dispatch()` validates access, making this a redundant but harmless check. More critically, if a developer instantiates `C_PracticeSettings` directly (outside the routing system), the new dispatch-based ACL check is bypassed entirely.

The whitelist approach in `VALID_CONTROLLERS` does limit which controllers can be dispatched, but only two controllers have ACL mappings in `CONTROLLER_ACL_MAP`. Controllers like 'document', 'hl7', 'pharmacy' etc. are whitelisted but have no ACL checks—they only rely on checks in their own constructors, which may not be executed if instantiated differently.

**Severity:** High - Privilege escalation possible if controllers are instantiated outside the routing layer.

**Recommendation:** 
- Ensure all controllers in `VALID_CONTROLLERS` have corresponding ACL mappings in `CONTROLLER_ACL_MAP`
- Add a final ACL check to the base Controller class that cannot be bypassed
- Document that controllers must only be instantiated through `dispatch()`

---

### 2. **Broken Access Control - Missing ACL for Whitelisted Controllers** - MEDIUM SEVERITY

**Location:** Lines 18-29 (VALID_CONTROLLERS) and 31-38 (CONTROLLER_ACL_MAP)

**Problem:**
The `VALID_CONTROLLERS` whitelist includes 9 controllers, but only 2 have ACL requirements defined:
- ✅ `practice_settings` → has ACL map
- ✅ `prescription` → has ACL map
- ❌ `document` → no ACL requirement
- ❌ `document_category` → no ACL requirement
- ❌ `hl7` → no ACL requirement
- ❌ `insurance_company` → no ACL requirement
- ❌ `insurance_numbers` → no ACL requirement
- ❌ `patient_finder` → no ACL requirement
- ❌ `pharmacy` → no ACL requirement
- ❌ `x12_partner` → no ACL requirement

This is by design (ACL check in constructor), but it means access control is inconsistent. If any controller's constructor ACL check is removed or bypassed, access is granted to unauthenticated users.

**Severity:** Medium - Inconsistent access control enforcement across controllers.

**Recommendation:**
- Centralize all ACL requirements in `CONTROLLER_ACL_MAP` 
- Update `checkControllerAcl()` to fail-secure by default: if a controller is not in the whitelist but also not explicitly exempted, deny access

---

### 3. **Injection - Insufficient Output Escaping** - MEDIUM SEVERITY

**Location:** Line 125-126 (error message construction)

```php
throw new NotFoundHttpException("Unable to load controller: $className");
```

and Line 162:

```php
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```

**Problem:**
While `$className` is constructed from a whitelist lookup (`self::VALID_CONTROLLERS[$controllerParam]`), so it's safe, the `$action` parameter is not validated and comes directly from user input (`$params['action']`). If the action name contains special characters, it could be reflected in error messages without escaping. Although this is in an exception message (not HTML), it could appear in logs or error handlers.

**Severity:** Medium - Potential XSS if exception messages are displayed in HTML context without escaping.

**Recommendation:**
```php
throw new NotFoundHttpException(
    "Action '" . htmlspecialchars($action, ENT_QUOTES, 'UTF-8') . 
    "' does not exist on controller: $className"
);
```

---

### 4. **Security Misconfiguration - Incomplete Type Safety** - MEDIUM SEVERITY

**Location:** Lines 147-150

```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
$processMethod = "{$actionMethod}_process";
```

**Problem:**
While the code checks `is_string($params['action'])`, the `$action` variable is still built directly into method names without validation. Although `call_user_func` and method_exists checks mitigate direct code execution, method names could still be manipulated (e.g., `__call`, `__get` magic methods). The regex sanitization in the old code (`preg_replace("/[^A-Za-z0-9_]/", ""`) is removed.

**Severity:** Medium - Potential for unexpected method invocation via magic methods.

**Recommendation:**
Add validation that `$action` contains only alphanumeric characters and underscores:
```php
if (!preg_match('/^[a-z0-9_]+$/i', $action)) {
    throw new BadRequestHttpException("Invalid action name");
}
```

---

### 5. **Broken Access Control - ACL Check Location** - LOW SEVERITY

**Location:** Lines 171-178

```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) {
    $output .= $callMethod($processMethod);
    if ($controllerObj->_state === false) {
        return $output;
    }
}
```

**Problem:**
The ACL check in `checkControllerAcl()` (line 110-121) runs *before* the controller is instantiated. If a controller's constructor modifies permissions or enforces additional checks (like `C_PracticeSettings` does), an attacker could potentially bypass those secondary checks by having `_state` set to `false` early. Additionally, the reliance on `_state` as a control flow mechanism is fragile.

**Severity:** Low - Works as designed but could be cleaner.

---

### 6. **Security Logging and Monitoring Failures** - LOW SEVERITY

**Location:** `dispatch()` method (lines 107-161)

**Problem:**
No logging is performed when:
- An invalid controller is requested (caught with exception, but not logged)
- An ACL check fails (relies on `AccessDeniedHelper`)
- An action doesn't exist (exception thrown, but not logged)

This makes security audit trails incomplete.

**Severity:** Low - Depends on global exception handling logging.

**Recommendation:**
Add logging before throwing exceptions:
```php
error_log("Security: Invalid controller requested: {$controllerParam}");
throw new BadRequestHttpException("...");
```

---

### 7. **Identification and Authentication Failures - Redundant ACL Checks** - LOW SEVERITY

**Location:** Comparing lines in `C_PracticeSettings.class.php` (constructor) and new `dispatch()` method

**Problem:**
`C_PracticeSettings::__construct()` performs ACL checks on lines 15-18, but the same checks are now done in `Controller::checkControllerAcl()`. This duplication creates maintenance risk: if one check is updated, the other may be forgotten.

**Severity:** Low - Current implementation is safe due to defense in depth, but creates confusion.

**Recommendation:**
Remove ACL check from controller constructors and rely solely on `dispatch()`. Update all controllers similarly.

---

## Positive Security Improvements

✅ **Whitelist-based controller validation** prevents arbitrary controller file inclusion
✅ **Centralized ACL mapping** makes security policies more visible
✅ **Exception-based error handling** prevents information leakage in some cases
✅ **Explicit parameter validation** (controller, action) vs. positional parsing

---

## Summary Table

| Issue | Category | Severity | Location |
|-------|----------|----------|----------|
| Missing ACL mappings for 7+ controllers | Broken Access Control | HIGH | Lines 18-38 |
| Direct controller instantiation bypasses dispatch ACL | Broken Access Control | HIGH | C_PracticeSettings.php:15-18 |
| Unsanitized `$action` in error messages | Injection (Reflected) | MEDIUM | Lines 125, 162 |
| No action name validation against alphanumeric | Security Misconfiguration | MEDIUM | Lines 149-150 |
| Missing security logging | Security Logging & Monitoring | LOW | Lines 107-161 |
| Redundant ACL checks in constructors | Identification & Authentication | LOW | C_PracticeSettings.php |