# Review: Controller Routing and ACL Refactoring

I've identified several issues across correctness, security, and maintainability:

---

## Critical Issues

### 1. **Missing Method Existence Check in dispatch()**
**Location:** Lines 197-200 (the `$callMethod` closure and its usage)  
**Problem:** The code uses `is_callable()` to check if `$processMethod` exists before calling it (line 197), but then calls `$actionMethod` without checking `is_callable()` first (line 203). If the action method doesn't exist, this will raise a fatal error instead of throwing the NotFoundHttpException.

**Severity:** HIGH (Correctness)

**Fix:** Add `is_callable()` check before line 203:
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
}
```

---

### 2. **Unsafe Dynamic Method Invocation**
**Location:** Lines 194-195 and 203  
**Problem:** Dynamic method invocation `$controllerObj->$method(...)` can be exploited if `$action` parameter is not properly sanitized. While the `action` parameter isn't explicitly whitelisted (unlike `controller`), arbitrary strings could potentially invoke unintended methods.

**Severity:** MEDIUM (Security)

**Recommendation:** Either:
- Whitelist valid actions per controller, or
- Add strict sanitization: `preg_replace("/[^A-Za-z0-9_]/", "", $action)`

---

### 3. **Inconsistent Parameter Handling Between act() and dispatch()**
**Location:** Lines 127-148 (act method) and 159-172 (dispatch method)  
**Problem:** The `act()` method renames 'action' parameter to 'sub_action' (line 144), but `dispatch()` doesn't have this logic. This breaks backward compatibility for callers using the legacy `act()` method with an 'action' parameter.

**Severity:** MEDIUM (Correctness)

**Fix:** Apply the same sub_action renaming logic in `dispatch()`:
```php
foreach ($params as $key => $value) {
    if (in_array($key, $reservedParams, true)) {
        continue;
    }
    $paramKey = ($key === 'action') ? 'sub_action' : $key;
    $args[$paramKey] = $value === '' ? null : $value;
}
```

---

## Moderate Issues

### 4. **Incomplete ACL Coverage**
**Location:** Lines 92-112 (CONTROLLER_ACL_MAP)  
**Problem:** Only 2 controllers have ACL mappings (`practice_settings`, `prescription`), but 9 are whitelisted in `VALID_CONTROLLERS`. The other 7 controllers bypass ACL checks entirely.

**Severity:** MEDIUM (Security)

**Recommendation:** Add ACL requirements for all 10 controllers, or add a comment explaining why some are intentionally unguarded.

---

### 5. **OEGlobalsBag Type Safety**
**Location:** Line 181  
**Problem:** `OEGlobalsBag::getInstance()->getString('fileroot')` assumes `getString()` method exists. The original code used `get()`, which is more forgiving. If the method doesn't exist, this will fail.

**Severity:** MEDIUM (Reliability)

**Recommendation:** Verify `getString()` exists in OEGlobalsBag or fall back to `get()` with a cast:
```php
$fileroot = OEGlobalsBag::getInstance()->get('fileroot');
$controllerFile = $fileroot . "/controllers/$className.class.php";
```

---

### 6. **String Interpolation in Exception Messages (Information Disclosure)**
**Location:** Lines 182  
**Problem:** Exception messages contain internal file paths and controller names that could leak system information to attackers if exception details are exposed.

**Severity:** LOW (Security)

**Recommendation:** Use generic messages for end users:
```php
throw new NotFoundHttpException("The requested resource could not be found.");
// Log details to internal log instead
error_log("Unable to load controller: $className");
```

---

## Minor Issues

### 7. **Incomplete Type Hints**
**Location:** Line 126 (act method parameter)  
**Problem:** The type hint `non-empty-array<string|int, mixed>` is a PHPDoc type, not enforced at runtime. The method will accept empty arrays and cause an error when accessing `$keys[0]`.

**Severity:** LOW (Maintainability)

**Recommendation:** Add runtime validation:
```php
if (empty($qarray)) {
    throw new BadRequestHttpException("No parameters provided");
}
```

---

### 8. **Unused Reference in Original Code Pattern**
**Location:** Line 197  
**Problem:** The original code used `&$c_obj` (reference) in `is_callable()`. The new code uses `$controllerObj` without reference. Verify this doesn't affect Smarty's internal state tracking.

**Severity:** LOW (Reliability)

---

## Summary Table

| Issue | Severity | Type | Location |
|-------|----------|------|----------|
| Missing method_exists check for actionMethod | HIGH | Correctness | 203 |
| Unsafe dynamic method invocation | MEDIUM | Security | 194-195, 203 |
| Inconsistent sub_action handling | MEDIUM | Correctness | 127-148 vs 159-172 |
| Incomplete ACL coverage | MEDIUM | Security | 92-112 |
| OEGlobalsBag method mismatch | MEDIUM | Reliability | 181 |
| Information disclosure in exceptions | LOW | Security | 182 |
| Unenforced type constraint | LOW | Maintainability | 126 |
| Reference parameter change | LOW | Reliability | 197 |