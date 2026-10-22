# Code Review: `Controller::act()` / `dispatch()` refactor

## High

### 1. Removed `method_exists()` guard makes the action check ineffective
**Location:** `dispatch()`, the `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])` checks.

**Problem:**
- The deleted comment explains the old guard: Smarty 4 implements `__call`, so `is_callable()` is **always true** on a `Controller`/`Smarty` subclass. That is why the old code also called `method_exists()`.
- The new code drops `method_exists()`. As a result:
  - The `NotFoundHttpException` branch for a missing action is effectively unreachable.
  - Any user-supplied `action=foo` is routed to `$controllerObj->foo_action(...)`, which lands in Smarty's `__call` / extension dispatcher with attacker-controlled arguments.
  - When processing, the same happens for a non-existent `*_action_process` method.
- At best this produces confusing Smarty errors. At worst it exposes Smarty's magic-method surface to request input.

**Fix:** Restore `method_exists($controllerObj, $method)`, or check via `ReflectionMethod` that the method exists and is public.

### 2. Action name is no longer sanitized
**Location:** `dispatch()`, `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`

**Problem:**
- The old code stripped everything except `[A-Za-z0-9_]` from the action. The new code uses the raw string to:
  - build a method name,
  - set `_current_action` (which templates and `_link()` may echo or use in URLs),
  - build exception messages.
- Combined with #1, arbitrary method names can be invoked.
- The unsanitized value is also reflected in `"Action '$action' does not exist..."`. If that message is rendered to HTML anywhere, this is a reflected XSS vector.

**Fix:**
- Validate against `/^[A-Za-z0-9_]+$/` and reject with `BadRequestHttpException` otherwise.
- Treat an empty string as `default`. Currently `action=` yields a method named `_action`.

### 3. `OpenEMR\Core\ControllerInterface` is not part of this PR
**Location:** class declaration, `implements ControllerInterface`.

**Problem:** The diff does not add this interface. If it doesn't already exist at this commit, every page that loads `Controller.class.php` fatals.

**Fix:** Confirm it exists. Also confirm that its method signatures match `act(array): string` and `dispatch(array): string`.

## Medium

### 4. Uncaught Symfony HTTP exceptions replace the old graceful errors
**Location:** `dispatch()`, the new `BadRequestHttpException` / `NotFoundHttpException` throws.

**Problem:**
- The old behavior was to echo a message (and `exit` for a missing controller file).
- Unless `controller.php` and every other caller of `act()`/`dispatch()` catch `HttpExceptionInterface`, these become uncaught fatals. Depending on configuration, that can leak stack traces and filesystem paths to users.
- Callers that expect a string, such as `C_PracticeSettings::*_action` sub-dispatch, will now abort mid-render instead of showing a message inside the page.

**Fix:** Verify the entry point(s) translate these exceptions into proper responses.

### 5. Legacy `act()` lets a query param named `controller` override the routed controller
**Location:** `act()`, the remaining-params loop.

**Problem:**
- `'action'` is renamed to `sub_action` to avoid collisions, but `'controller'` (and `'process'`) are not.
- Example: `controller.php?document&list&controller=pharmacy` overwrites `$params['controller']`, so the request is routed to Pharmacy.
- The ACL map is still consulted for the final controller, so this is not a direct ACL bypass. It is still surprising routing and inconsistent with the `action` handling.

**Fix:** Skip or rename the `controller` key in `act()`.

### 6. Hard-coded whitelist may omit existing controllers
**Location:** `VALID_CONTROLLERS`.

**Problem:**
- Previously, any `controllers/C_*.class.php` file was routable.
- Any controller file or legacy URL not in this list now returns 400. This includes controllers used by modules, custom code, or less common links.

**Fix:**
- Audit `controllers/` and all `controller.php?...` links (templates, JS, `_link()` usages) to make sure nothing was dropped.
- Consider a test that asserts the whitelist matches the directory contents.

## Low

### 7. `_state` comparison semantics changed
**Location:** `dispatch()`, `if ($controllerObj->_state === false)`.

**Problem:**
- The old check was `== false`. Under the old code, a `_state` of `null`, `0`, or `''` stopped execution after the `_process` method.
- Under the new code, those values let the main action run as well. Any controller that sets `_state` to a falsy non-boolean, or never initializes it, now behaves differently after processing.

**Fix:** Confirm `_state` is always initialized to a boolean, or keep the loose comparison.

### 8. Numeric keys are not skipped in `act()`
**Location:** `act()`, the `$key === $controller` / `$key === $positionalAction` comparisons.

**Problem:**
- PHP converts numeric-string array keys to `int`.
- `$controller` and `$positionalAction` are cast to string, so the strict comparison fails for int keys.
- An int key in the first or second position is then also passed as an argument.

**Fix:** Compare `(string) $key`.

### 9. Empty `$qarray` triggers a warning
**Location:** `act()`, `$keys[0]`.

**Problem:** When `$qarray` is empty, `$keys[0]` raises an "undefined array key" warning before the 400 is thrown.

**Fix:** Guard for an empty array explicitly.

### 10. New typed signatures may break subclasses
**Location:** `act(array $qarray): string` and `dispatch(array $params): string`.

**Problem:** Any subclass that overrides `act()` with an untyped or incompatible signature will now fatal at load time.

**Fix:** Grep for overrides.

### 11. ACL is duplicated between the map and the controller
**Location:** `CONTROLLER_ACL_MAP` vs. the `C_PracticeSettings` constructor.

**Problem:** The `admin/practice` check exists in both places, so the two can drift.

**Fix:** Note this in a comment, or remove one copy as a follow-up.