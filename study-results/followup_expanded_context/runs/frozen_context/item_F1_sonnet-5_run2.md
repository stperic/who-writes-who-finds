## Review Comments

### 1. **High — Missing `method_exists()` checks reintroduces a previously-fixed Smarty 4 bug**
**Location:** `Controller::dispatch()`, the `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])` checks.

The old code explicitly checked **both** `is_callable()` *and* `method_exists()`, with a comment explaining why:

> "can no longer rely on is_callable since smarty 4 invokes a `__call` function deep within its classes, thus is_callable() is always true. so need to do both the is_callable and a method_exists() check."

The new `dispatch()` drops the `method_exists()` check entirely. Because `Controller` extends `Smarty`, which implements `__call()`, `is_callable()` will return `true` for virtually any method name, valid or not. Practical consequences:

- The `else { throw new NotFoundHttpException(...) }` branch for an invalid/mistyped action becomes effectively unreachable — invalid actions will silently fall through into a call to a non-existent method, invoked via Smarty's `__call()` magic method instead of producing the intended 404.
- The `_action_process` branch will now almost always be considered "callable" even when no such process method exists, causing an unintended call into Smarty internals with the action's arguments.

This is a functional regression of a bug that was deliberately fixed previously, and it undermines the very "action does not exist" error handling this PR introduces.

---

### 2. **Medium — Silent discarding of non-string action return values**
**Location:** `$callMethod` closure in `dispatch()`:
```php
$result = $controllerObj->$method(...array_values($args));
return is_string($result) ? $result : '';
```
Previously, output was built via `.=`, so any non-string return (int, bool, float, or an object with `__toString`) would be auto-cast to a string and concatenated. Now, any non-string return is silently discarded as `''`. If any existing action method returns something other than a string (there's no guarantee all of them do), its output will quietly disappear — a behavior change with no error/log to indicate it happened.

---

### 3. **Medium — No sanitization/whitelisting of the `action` value**
**Location:** `dispatch()`:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
```
Unlike the controller name (now validated against `VALID_CONTROLLERS`), the action string is used directly, unsanitized, to build a method name for dynamic invocation. In the old code this was at least passed through `preg_replace("/[^A-Za-z0-9_]/", "", ...)`. Combined with issue #1 (broken `is_callable` guard), arbitrary/mistyped action strings can reach `$controllerObj->$method(...)` and be swallowed by `__call()`. Even if `__call()` is ultimately benign, relying on it for input validation is fragile. Consider re-adding basic sanitization or an explicit action whitelist per controller.

---

### 4. **Low/Medium — Strict type comparison on array keys in `act()`**
**Location:** 
```php
foreach ($qarray as $key => $value) {
    if ($key === $controller || $key === $positionalAction) {
```
`$controller`/`$positionalAction` are forced to `string`, but PHP auto-casts purely-numeric string array keys (e.g., `"0"`) to `int`. If a query string ever contains a numeric key matching the controller/action position (edge case, but possible via `$_GET`), the strict `===` comparison will fail to match, causing the controller/action keys to be duplicated into the forwarded `$params`/args. Worth using a loose comparison or casting `$key` to string before comparing.

---

### 5. **Low — Behavior/error-handling change not fully verified against call sites**
**Location:** `dispatch()` now throws `BadRequestHttpException` / `NotFoundHttpException` where the old code used `echo ...; exit;`.

This is an improvement in principle, but it's a meaningful change in control flow — any code calling `act()`/`dispatch()` must now be wrapped by something that catches these exceptions and renders a proper error page; otherwise an uncaught exception could produce a raw PHP error/stack trace in production (information disclosure) rather than the previous simple message. No changes to `controller.php` (the actual entry point) are included in this diff to confirm this is handled.

---

### 6. **Low — Redundant ACL enforcement**
**Location:** `checkControllerAcl()` in `Controller.class.php` vs. the ACL check already performed in `C_PracticeSettings::__construct()`.

Both places enforce `admin/practice`. Not incorrect, but it's a duplicate source of truth — if one is updated (e.g., ACL changed) and the other isn't, behavior could diverge. Worth consolidating now that `checkControllerAcl()` exists as the "single" mechanism.

---

### 7. **Nit — Fragile positional→named mapping logic in `act()`**
**Location:** `act()`, the `sub_action` renaming logic.

The rename of `'action'` → `'sub_action'` to avoid colliding with the routing `action` key (for nested dispatch patterns like `practice_settings` → `pharmacy` → `list`) is clever but non-obvious and easy to break in future refactors. Given this is marked `@deprecated` legacy code, it would be good to add a regression test covering this exact nested-controller scenario (`C_PracticeSettings::pharmacy_action`, etc.) before merging, since it's the one case in the provided context files that actually exercises this path.

---

No issues found with the introduction of the `VALID_CONTROLLERS` whitelist itself — it's a solid improvement over the old regex-based class-name sanitization and meaningfully reduces file-path-injection risk.