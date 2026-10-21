# Code Review: Controller.class.php

## Issues Found

### 1. **Security: Unvalidated Dynamic Method Invocation (HIGH)**
**Location:** Lines 210-211, 213
```php
$output .= $callMethod($processMethod);
...
$output .= $callMethod($actionMethod);
```

**Problem:** The code calls dynamically-constructed method names without verifying they exist before invocation. While `is_callable()` is checked for the process method, it's NOT checked for the main action method (line 213). If a controller doesn't implement the action method, it will trigger a fatal error instead of throwing the intended `NotFoundHttpException`.

**Severity:** HIGH - Can cause information disclosure via error messages and breaks intended exception handling.

**Fix:** Add `method_exists()` check before calling `$callMethod($actionMethod)`:
```php
if (is_callable([$controllerObj, $actionMethod]) && method_exists($controllerObj, $actionMethod)) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
}
```

---

### 2. **Security: Unsafe String Interpolation in Exception Messages (MEDIUM)**
**Location:** Lines 169, 175, 216
```php
throw new BadRequestHttpException("Missing or invalid 'controller' parameter");
throw new NotFoundHttpException("Unable to load controller: $className");
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```

**Problem:** While `$className` and `$action` are derived from validated sources, using string interpolation in error messages is fragile and could leak information. More importantly, the error messages themselves might be exposed to users in debug mode.

**Severity:** MEDIUM - Information disclosure risk in error responses.

---

### 3. **Logic Bug: Incorrect Condition on Line 213 (MEDIUM)**
**Location:** Line 213
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
```

**Problem:** The condition uses `||` (OR) which means if `$isProcessing` is true, it will attempt to call the action method even if it doesn't exist. The logic should be `&&` (AND) to only proceed if BOTH processing is happening AND the method exists. The original code had separate `if` statements for this reason.

**Severity:** MEDIUM - Will cause fatal errors when action method doesn't exist during POST processing.

**Fix:**
```php
if ($isProcessing && is_callable([$controllerObj, $actionMethod]) && method_exists($controllerObj, $actionMethod)) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
}
```

---

### 4. **Code Quality: Inconsistent Method Existence Checking (MEDIUM)**
**Location:** Lines 207, 213
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) {
    // Missing method_exists() check
    
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    // Has is_callable but logic is wrong
```

**Problem:** The original code checked both `is_callable()` AND `method_exists()` for good reason (comment on line 104-105 explains Smarty 4 compatibility). The refactored code is missing `method_exists()` checks consistently.

**Severity:** MEDIUM - Breaks Smarty 4 compatibility workaround.

---

### 5. **Maintainability: Whitelist Mapping Duplication Risk (LOW)**
**Location:** Lines 18-26 and 35-37
```php
private const VALID_CONTROLLERS = [
    'practice_settings' => 'PracticeSettings',
    'prescription' => 'Prescription',
    ...
];

private const CONTROLLER_ACL_MAP = [
    'practice_settings' => ['admin', 'practice', 'Practice Settings'],
    'prescription' => ['patients', 'rx', 'Prescriptions'],
];
```

**Problem:** Controller names are duplicated across two constants. If someone adds a controller to `VALID_CONTROLLERS`, they might forget to add ACL rules to `CONTROLLER_ACL_MAP`, or vice versa. No enforcement mechanism exists.

**Severity:** LOW - Future maintenance issue, not a current bug.

---

### 6. **Type Safety: Unsafe Array Access (LOW)**
**Location:** Lines 131-132
```php
$keys = array_keys($qarray);
$controller = (string) $keys[0];
$positionalAction = (string) ($keys[1] ?? 'default');
```

**Problem:** If `$qarray` is empty (despite the type hint indicating non-empty), `$keys[0]` will cause an undefined array key error. The type hint says `non-empty-array` but there's no runtime validation.

**Severity:** LOW - Type hints should prevent this, but defensive programming would be better.

---

## Summary

| Severity | Count | Issue |
|----------|-------|-------|
| HIGH | 1 | Missing method_exists() check before action method invocation |
| MEDIUM | 3 | Logic operator error, inconsistent method checking, information disclosure |
| LOW | 2 | Whitelist duplication risk, unsafe array access |

**Recommendation:** Do not merge until HIGH severity issue is fixed. The logic bug on line 213 should also be addressed before merge.