# Pull Request Review

I've identified several issues that should be addressed before merging:

## 1. **CRITICAL: Method Call Vulnerability** 
**Location:** Lines 199-201 and 205-207 in `dispatch()`

**Problem:** The code calls `$controllerObj->$method(...)` using a dynamically constructed method name without verifying the method exists first. While `is_callable()` is checked before calling `$processMethod`, the subsequent call to `$actionMethod` (line 205) only checks `is_callable()` as a condition but doesn't verify it before calling on line 207.

```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);  // Will fail if method doesn't exist
}
```

**Severity:** HIGH - This can cause a fatal error or undefined behavior.

**Fix:** Add `method_exists()` check inside `$callMethod()` or before calling it.

---

## 2. **Logic Error in Action Method Selection**
**Location:** Lines 204-207 in `dispatch()`

**Problem:** The condition `if ($isProcessing || is_callable(...))` means that if `$isProcessing` is true, it will attempt to call the action method even if it's not callable. This could throw an error if the action method doesn't exist but `$_POST['process']` was set.

**Severity:** HIGH - Inconsistent with the process method handling above.

**Fix:** Change to `if (!$isProcessing || is_callable(...))` or restructure the logic.

---

## 3. **Type Safety Issue in `act()` Return Type**
**Location:** Line 136 in `act()`

**Problem:** The method signature declares return type `string`, but there's no guarantee all code paths return a string. If `dispatch()` throws an exception, nothing is returned.

**Severity:** MEDIUM - Violates the type contract and could cause issues for callers.

---

## 4. **Missing Method Existence Check**
**Location:** Lines 199-201 in `dispatch()`

**Problem:** The `$callMethod` closure doesn't validate that the method exists before attempting to call it. It relies entirely on the caller to check `is_callable()`, but this is error-prone.

**Severity:** MEDIUM - Fragile design; better to encapsulate the check.

---

## 5. **Potential Type Coercion Issue**
**Location:** Line 167 in `dispatch()`

**Problem:** The line `$controllerParam = is_string($params['controller'] ?? null) ? $params['controller'] : '';` assigns an empty string if controller isn't a string. This will fail the whitelist check and throw an exception, which is correct behavior, but the empty string is misleading.

**Severity:** LOW - Works correctly but could be clearer.

---

## 6. **Inconsistent Parameter Handling in `act()`**
**Location:** Lines 148-152 in `act()`

**Problem:** The code skips parameters that match the controller or action keys by identity (`$key === $controller`), but `$controller` is cast to string while array keys might be integers. This could cause unexpected behavior if positional keys are used.

**Severity:** LOW - Unlikely to cause issues in practice but semantically unclear.

---

## Recommendations

1. Add explicit `method_exists()` checks before any dynamic method calls
2. Fix the logic in the conditional (line 204) to prevent calling non-existent methods
3. Consider using `call_user_func()` or similar with proper error handling
4. Add unit tests for edge cases (missing controller, missing action, etc.)