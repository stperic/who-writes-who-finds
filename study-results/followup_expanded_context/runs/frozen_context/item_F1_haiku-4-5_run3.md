I've identified several issues in this pull request:

---

## 1. **CRITICAL: Logic Error in Action Method Invocation**
**Location:** Line 227 in `dispatch()` method
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
```
**Problem:** The condition uses `||` (OR) when it should use `&&` (AND). Currently, if `$isProcessing` is true, the action method will be called even if it doesn't exist. The original code only called the action method if the process method didn't exist or if not processing.

**Severity:** HIGH - Will cause runtime errors when `_action` methods don't exist during POST processing.

---

## 2. **CRITICAL: Method Existence Check Removed**
**Location:** Lines 227-228 in `dispatch()` method
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
```
**Problem:** The refactored code removed the `method_exists()` check. While `is_callable()` is used, the code doesn't verify the method exists before calling `$callMethod()`, which will cause a fatal error if the method doesn't exist.

**Severity:** HIGH - Will cause fatal PHP errors.

---

## 3. **Logic Error: Process Flag Handling**
**Location:** Lines 217-220 in `dispatch()` method
```php
// Handle process flag
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
```
**Problem:** The code unssets `$params['process']` after checking for it, but then later checks `$_POST['process']` which was set by the code itself. However, if `$params['process']` is set from `$_GET`, the logic should preserve that intent. The original code's behavior is unclear here.

**Severity:** MEDIUM - May cause unexpected behavior in process flow.

---

## 4. **Type Safety Issue in `act()` Method**
**Location:** Line 127-128 in `act()` method
```php
$keys = array_keys($qarray);
$controller = (string) $keys[0];
```
**Problem:** No validation that `$qarray` is non-empty before accessing `$keys[0]`. The type hint says `non-empty-array` but PHP won't enforce this at runtime. An empty array will cause an undefined array access.

**Severity:** MEDIUM - Could cause PHP warnings/errors if empty array is passed.

---

## 5. **Incomplete Error Handling**
**Location:** Line 215 in `dispatch()` method
```php
throw new NotFoundHttpException("Unable to load controller: $className");
```
**Problem:** When `i_once()` returns false, the code throws an exception. However, looking at the controller files in context (C_PracticeSettings), they perform their own ACL checks in the constructor. If a controller is loaded and the constructor itself denies access via `AccessDeniedHelper::denyWithTemplate()`, this will exit before returning to the dispatch method. This is inconsistent with the new exception-based error handling approach.

**Severity:** MEDIUM - Inconsistent error handling strategy between framework and individual controllers.

---

## 6. **Array Values Loss with Named Parameters**
**Location:** Lines 224-225 in `dispatch()` method
```php
$result = $controllerObj->$method(...array_values($args));
return is_string($result) ? $result : '';
```
**Problem:** The original code built `$args_array` as an indexed array matching parameter order. The new code converts `$args` (which is keyed) to `array_values($args)`. This will work but loses the semantic meaning that params are keyed. More importantly, the order of parameters in `array_values()` depends on the iteration order of `$params`, which may not match the original positional parameter order expected by controller methods.

**Severity:** MEDIUM-HIGH - Could cause parameters to be passed in wrong order to action methods.

---

## 7. **Missing Input Validation**
**Location:** Lines 153-158 in `act()` method
```php
foreach ($qarray as $key => $value) {
    if ($key === $controller || $key === $positionalAction) {
        continue;
    }
    // Rename explicit 'action' to avoid collision...
    $params[$key === 'action' ? 'sub_action' : $key] = $value;
}
```
**Problem:** Parameters are not sanitized. The original code used `preg_replace("/[^A-Za-z0-9_]/", "", ...)` to sanitize parameter names. This sanitization is now missing, which could allow injection of arbitrary keys.

**Severity:** MEDIUM - Potential for parameter pollution or unexpected behavior.

---

## 8. **Inconsistent Parameter Handling Between `act()` and `dispatch()`**
**Location:** Lines 148-151 in `act()` method vs. Lines 220-223 in `dispatch()` method
```php
// act() renames 'action' to 'sub_action'
$params[$key === 'action' ? 'sub_action' : $key] = $value;

// dispatch() doesn't handle this renaming
$args[$key] = $value === '' ? null : $value;
```
**Problem:** The `act()` method applies a transformation that `dispatch()` doesn't handle. This makes the behavior inconsistent when calling `dispatch()` directly versus through `act()`.

**Severity:** MEDIUM - Inconsistent API behavior.

---

## Summary
The most critical issues are **#1** (logic error in conditional), **#2** (missing method existence check), and **#6** (parameter order not preserved). Issue **#7** (missing input sanitization) is also a security concern.