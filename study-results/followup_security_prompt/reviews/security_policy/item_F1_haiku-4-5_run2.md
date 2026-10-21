# Security Review - Pull Request Diff

## Summary
This refactoring introduces a whitelist-based controller dispatch system with ACL checks. While it improves security posture overall, there are several issues to address.

---

## Issues Found

### 1. **Broken Access Control - Incomplete ACL Coverage**
**Location:** Lines 34-37 (`CONTROLLER_ACL_MAP`)  
**OWASP Category:** A01:2021 - Broken Access Control  
**Severity:** High

**Problem:**  
The `CONTROLLER_ACL_MAP` only covers 2 controllers (`practice_settings`, `prescription`), but `VALID_CONTROLLERS` whitelist contains 9 controllers. Controllers not in the ACL map return early from `checkControllerAcl()` without any authorization check, allowing unrestricted access.

```php
if (!isset(self::CONTROLLER_ACL_MAP[$controllerName])) {
    return;  // No ACL check performed for unlisted controllers
}
```

**Recommendation:**  
Either:
- Add ACL requirements for all 9 controllers to the map, or
- Change the logic to deny by default: `if (!isset(self::CONTROLLER_ACL_MAP[$controllerName])) { throw new AccessDeniedException(); }`

---

### 2. **Broken Access Control - Unsafe Action Method Invocation**
**Location:** Lines 174-175 (method call via variable)  
**OWASP Category:** A01:2021 - Broken Access Control  
**Severity:** High

**Problem:**  
Action method names are constructed from user input (`$params['action']`) without validation against a whitelist. An attacker could invoke arbitrary methods:

```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";  // No whitelist validation
$callMethod($actionMethod);  // Invokes arbitrary method
```

Example attack: `?controller=document&action=__construct` or `?action=somePrivateMethod`

**Recommendation:**  
Implement a whitelist of valid actions per controller, or enumerate available actions via reflection and validate against them.

---

### 3. **Injection - Dynamic Variable Method Invocation (Method Name)**
**Location:** Lines 186, 189  
**OWASP Category:** A03:2021 - Injection  
**Severity:** Medium

**Problem:**  
While the action name sanitization has improved (removed the old regex `preg_replace("/[^A-Za-z0-9_]/")`), the new code still constructs method names dynamically without verification that the method exists before calling it. The `is_callable()` check runs after construction, but doesn't prevent invocation of unintended methods.

**Recommendation:**  
Before calling `$callMethod()`, verify the method exists and is intended for dispatch:
```php
if (!method_exists($controllerObj, $actionMethod)) {
    throw new NotFoundHttpException("Action not found: $actionMethod");
}
```

---

### 4. **Security Misconfiguration - Incomplete Process Flag Handling**
**Location:** Lines 145-147  
**OWASP Category:** A05:2021 - Security Misconfiguration  
**Severity:** Medium

**Problem:**  
The code unsets `$_GET['process']` and `$params['process']` but then sets `$_POST['process']`, which persists across the request lifecycle. If the controller action method doesn't properly consume this flag, unexpected form processing could occur on subsequent calls or in nested controller chains.

**Recommendation:**  
Document that controllers must consume the `process` flag and consider using a request-scoped state object instead of superglobals.

---

### 5. **Broken Access Control - Inconsistent Parameter Handling in act()**
**Location:** Lines 126-139  
**OWASP Category:** A01:2021 - Broken Access Control  
**Severity:** Medium

**Problem:**  
The `act()` method extracts the first two array keys as controller/action:
```php
$controller = (string) $keys[0];
$positionalAction = (string) ($keys[1] ?? 'default');
```

PHP array key order depends on insertion order. An attacker could exploit this by controlling the order of `$_GET` parameters. Additionally, the old code used `array_reverse()` and `array_pop()`, which had different semantics—this behavioral change could introduce bypasses if legacy code relied on the old ordering.

**Recommendation:**  
Migrate all callers to use `dispatch()` directly with explicit `controller` and `action` parameters, then deprecate `act()`.

---

### 6. **Server-Side Request Forgery (SSRF) / Path Traversal**
**Location:** Lines 149-151  
**OWASP Category:** A10:2021 - Server-Side Request Forgery  
**Severity:** Medium

**Problem:**  
The controller filename is constructed using the whitelist, which is good. However, the file path is built using string concatenation:

```php
$controllerFile = OEGlobalsBag::getInstance()->getString('fileroot') . "/controllers/$className.class.php";
if (!$this->i_once($controllerFile)) {
```

While the `$className` is derived from the validated whitelist, relying on `i_once()` (include_once) is risky if that function doesn't properly validate paths. The `realpath()` comparison should be used to prevent symlink attacks.

**Recommendation:**  
```php
$expectedFile = OEGlobalsBag::getInstance()->getString('fileroot') . "/controllers/$className.class.php";
$realPath = realpath($expectedFile);
$expectedRealPath = realpath(dirname($expectedFile));

if (!$realPath || strpos($realPath, $expectedRealPath) !== 0) {
    throw new NotFoundHttpException("Invalid controller path");
}
require_once $realPath;
```

---

### 7. **Identification and Authentication Failures - Missing User Context**
**Location:** Lines 118-124  
**OWASP Category:** A07:2021 - Identification and Authentication Failures  
**Severity:** Medium

**Problem:**  
The ACL check only verifies permissions but doesn't verify user is authenticated before attempting ACL checks. If `AclMain::aclCheckCore()` doesn't handle unauthenticated users gracefully, it could leak information or cause unexpected behavior.

**Recommendation:**  
Add explicit authentication check before ACL evaluation:
```php
if (!isset($_SESSION['authId']) || !$_SESSION['authId']) {
    throw new AuthenticationException("User not authenticated");
}
```

---

### 8. **Security Logging and Monitoring Failures**
**Location:** Throughout dispatch() method  
**OWASP Category:** A09:2021 - Security Logging and Monitoring Failures  
**Severity:** Low

**Problem:**  
No logging of:
- Failed ACL checks
- Invalid controller/action requests
- Exceptions thrown

**Recommendation:**  
Add logging for security events:
```php
error_log("ACL check failed for controller=$controllerParam, user=$userId");
```

---

## Summary Table

| Issue | Location | Category | Severity | Status |
|-------|----------|----------|----------|--------|
| Incomplete ACL coverage | Line 118 | Broken Access Control | High | 🔴 Must Fix |
| Unsafe action method invocation | Line 174 | Broken Access Control | High | 🔴 Must Fix |
| Dynamic method name injection | Line 186 | Injection | Medium | 🟡 Should Fix |
| Process flag persistence | Line 146 | Security Misconfiguration | Medium | 🟡 Should Fix |
| Parameter order exploitation | Line 127 | Broken Access Control | Medium | 🟡 Should Fix |
| Path traversal risk | Line 150 | SSRF | Medium | 🟡 Should Fix |
| Missing auth check | Line 119 | Authentication Failures | Medium | 🟡 Should Fix |
| Missing security logging | Throughout | Security Logging | Low | 🟢 Nice to Have |