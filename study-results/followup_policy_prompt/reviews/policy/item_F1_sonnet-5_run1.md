## Summary

This is a solid refactor (whitelist-based controller resolution, named `dispatch()` API, deprecation of positional `act()`), but it reintroduces/creates several correctness and security regressions relative to the code it replaces, mostly in the action-method dispatch logic.

---

### 1. Dropped `method_exists()` check alongside `is_callable()` — **High**
**Location:** `dispatch()`, process/action invocation block.

The old code explicitly checked both:
```php
if (is_callable([&$c_obj, $c_action . "_action_process"]) && method_exists($c_obj, $c_action . "_action_process")) {
```
with a comment explaining *why* both are required: Smarty 4 implements `__call()`, which makes `is_callable()` return `true` for **any** method name, even ones that don't exist. The new code only checks `is_callable()`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... }
```
This silently reintroduces the exact bug the original comment warned about: any `_action`/`_action_process` method name will appear "callable," and the code will attempt to invoke it even if it doesn't exist. Combined with issue #2 below, this is more than cosmetic.

### 2. Action name is no longer sanitized — **High (security-relevant)**
**Location:** `dispatch()`

Previously:
```php
$c_action = preg_replace("/[^A-Za-z0-9_]/", "", (string) array_pop($args));
```
Now:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
```
`$action` comes straight from request input (`$_GET['action']` typically) with no character filtering before being turned into a method name and invoked via `$controllerObj->$method(...)`. Combined with the missing `method_exists()` check, this means attacker-controlled strings are passed to PHP's dynamic method call mechanism and will hit Smarty's `__call()` magic method unsanitized. This needs the same sanitization the legacy code performed, plus an explicit `method_exists()` check restored.

### 3. Dead/short-circuited callable check on process path — **Medium**
**Location:** `dispatch()`
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException(...);
}
```
When `$isProcessing` is `true`, the `is_callable()` check is never evaluated due to short-circuit `||`, so the action method is invoked unconditionally — if it doesn't exist, this becomes a fatal "call to undefined method" rather than the intended `NotFoundHttpException`. (This mirrors old behavior, so it's not a new bug per se, but since the refactor's stated goal is safer error handling, it should have been fixed here rather than carried forward.)

### 4. `_state` comparison changed from loose to strict — **Medium**
**Location:** `dispatch()`
```php
if ($controllerObj->_state === false) {
    return $output;
}
```
Original used `== false`, which short-circuits for `null`, `0`, `""`, `false`, etc. The new strict `=== false` only short-circuits on literal boolean `false`. Any controller that previously relied on setting `_state = null` or `0` to signal "stop processing" will now silently continue into the `_action` call, changing behavior/output for existing controllers.

### 5. `dispatch()` mutates global superglobals even when not operating on `$_GET`/`$_POST` — **Medium (design/testability)**
**Location:** `dispatch()`
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
...
$isProcessing = ($_POST['process'] ?? '') === 'true';
```
`dispatch()` is advertised as a generic, order-independent API taking an arbitrary `$params` array, yet it reaches into and mutates `$_GET`/`$_POST` directly regardless of whether `$params` actually *is* `$_GET`. This breaks encapsulation, makes the method impossible to unit test cleanly, and could produce surprising side effects if `dispatch()` is ever called with a synthetic params array (e.g., from an internal caller or test) that happens to contain a `process` key.

### 6. Potential undefined-array-key warning on empty `$qarray` in `act()` — **Low**
**Location:** `act()`
```php
$keys = array_keys($qarray);
$controller = (string) $keys[0];
```
If `$qarray` is empty (the PHPDoc claims `non-empty-array` but this isn't enforced), `$keys[0]` is undefined, triggering a PHP warning/notice (and under OpenEMR's error-to-exception handlers, possibly a fatal error) before the whitelist check can produce a clean `BadRequestHttpException`. The old code handled this gracefully via `array_key_first($qarray) ?? ''`.

### 7. Unhandled-exception risk / possible information disclosure — **Medium (needs verification)**
**Location:** `dispatch()` (`BadRequestHttpException`, `NotFoundHttpException`)

The diff replaces `echo ...; exit;` with thrown exceptions. This is an improvement in principle, but nothing in this diff shows where these exceptions are caught. If the calling script (`controller.php` or similar) doesn't have a handler converting these into safe error pages, they will surface as uncaught exceptions, potentially leaking stack traces/file paths in environments where `display_errors` is on. Please confirm the entry point(s) calling `act()`/`dispatch()` have been updated with appropriate try/catch handling.

### 8. Fragile implicit "action → sub_action" rename in `act()` — **Low (maintainability)**
**Location:** `act()`
```php
$params[$key === 'action' ? 'sub_action' : $key] = $value;
```
This is a non-obvious, special-cased workaround for one specific legacy flow (`practice_settings` → `pharmacy` → `list`) baked into a generic-looking shim. It's undocumented at the call sites that rely on it and easy to break in future refactors. Worth a more explicit mechanism or at least a test covering this specific case.

---

### Positive notes
- Moving from regex-sanitized-but-unbounded class name construction to an explicit `VALID_CONTROLLERS` whitelist is a genuine security improvement over the original (previously, any file matching `C_<sanitized name>.class.php` in the controllers directory could be loaded).
- ACL-check logic is cleanly extracted and behaviorally equivalent to before.

### Recommendation
Before merging, restore the `method_exists()` + sanitize-action-name safeguards (items 1–2), fix the strict `_state` comparison (item 4), and confirm exception handling is wired up at the call sites (item 7). These are the issues I'd consider blocking.