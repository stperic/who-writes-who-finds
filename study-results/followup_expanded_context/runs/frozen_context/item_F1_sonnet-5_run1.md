## Review comments

### 1. `is_callable()` check without `method_exists()` reintroduces the exact Smarty‑4 bug the old code worked around
**Location:** `Controller::dispatch()`, the `$isProcessing` branches:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... } else { throw new NotFoundHttpException(...); }
```
The original code had an explicit comment and combined `is_callable() && method_exists()` because **Smarty 4's `__call()` makes `is_callable()` always return `true`**, even for non-existent methods. This PR drops `method_exists()`. Consequences:
- The `else` branch that throws `NotFoundHttpException` for an invalid action can effectively never run (since `is_callable()` is always true for Smarty-derived objects), so the dispatcher will silently “succeed” and fall through into Smarty’s magic `__call()` with unpredictable results instead of reporting a proper 404.
- `_action_process` methods that don’t actually exist will also be invoked via `__call()`.
- Since `action` is a user-controlled GET/POST parameter with no whitelist (unlike `controller`), this is effectively uncontrolled input flowing into Smarty's internal `__call` dispatch.

**Severity:** High — functional regression and a reduction of input validation on a previously-hardened path.

---

### 2. Hard-coded controller whitelist may not match all existing controllers
**Location:** `Controller::VALID_CONTROLLERS`
Previously *any* file under `controllers/` matching the sanitized name could be routed to. Now only the 10 names listed are reachable; anything else throws `BadRequestHttpException`. There’s no verification in the diff that this list is exhaustive relative to the actual `controllers/` directory (and any third-party/custom controllers used by OpenEMR modules). If incomplete, this silently breaks existing routes.

**Severity:** High (regression risk) — needs confirmation that the whitelist was generated against the full controller directory, including module/plugin controllers.

---

### 3. Unhandled exceptions may leak internal detail or produce ugly failures
**Location:** `dispatch()` — `throw new BadRequestHttpException(...)`, `throw new NotFoundHttpException(...)`
The old code used `echo ...; exit;` (not great either, but predictable). The new code throws Symfony HTTP exceptions. There’s no evidence in this diff (or the provided context) that `controller.php`/callers catch these and render a safe error page. If uncaught, depending on `display_errors`/debug settings this could produce a raw stack trace (information disclosure) rather than a controlled error response — a concern for a healthcare application.

**Severity:** Medium — needs verification that the entry point (`controller.php`) has exception handling/logging in place.

---

### 4. Loss of character sanitization on `action`
**Location:** `dispatch()`:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
```
The old code ran `preg_replace("/[^A-Za-z0-9_]/", "", ...)` on both controller and action names before using them to build class/method names. The controller name is now whitelist-validated (fine), but `action` is used verbatim to build a method name with no sanitization. Combined with issue #1 (`is_callable` always true via `__call`), arbitrary strings can now reach `$controllerObj->$method(...)`. Low direct risk since PHP won’t execute arbitrary code via this construct, but it is a regression in defense-in-depth that should be restored or explicitly justified.

**Severity:** Low–Medium.

---

### 5. Fragile positional-argument matching is preserved, not fixed
**Location:** `dispatch()` building `$args` from `$params` and calling `...array_values($args)`
Arguments are still matched to the target method purely by **array iteration order**, not by name. This was true before (via `array_reverse`/`array_pop`), but the refactor doesn’t address it — for `dispatch()` called directly with `$_GET`, result depends on the query-string ordering. This is fine for backward compatibility but worth flagging as remaining tech debt, since the new “order independent routing” claim in the docblock is only true for `controller`/`action`, not for the remaining method arguments.

**Severity:** Low (design/maintainability note, not a new bug).

---

### 6. Edge case: default sentinel can collide with a real parameter name
**Location:** `act()`:
```php
$positionalAction = (string) ($keys[1] ?? 'default');
...
foreach ($qarray as $key => $value) {
    if ($key === $controller || $key === $positionalAction) { continue; }
```
If there is no second key, `$positionalAction` becomes the literal string `'default'`. If `$qarray` happens to contain a key literally named `default` (unrelated to the action), it will be incorrectly skipped from `$params`.

**Severity:** Low.

---

### 7. Duplicate ACL enforcement
**Location:** `Controller::checkControllerAcl()` vs `C_PracticeSettings::__construct()` (context file)
Both the new centralized `CONTROLLER_ACL_MAP` and `C_PracticeSettings`’s own constructor independently enforce `admin/practice`. Not a bug (defense in depth), but worth consolidating now that there’s a central mechanism — otherwise future edits to one location may create the false impression that ACL is fully centralized when it isn’t.

**Severity:** Low (maintainability).

---

### Summary
The refactor is a good overall direction (whitelisting, explicit exceptions, clearer `dispatch()` API), but it reintroduces a previously-fixed Smarty `__call` bug (#1) that defeats the “unknown action” error path and input validation, and the controller whitelist (#2) is a risk if incomplete. These two should be resolved/verified before merge; the rest are lower-priority cleanup items.