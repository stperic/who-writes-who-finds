# Code Review: `Controller::act()` / `dispatch()` refactor

The whitelist and the table-driven ACL are improvements. However, several regressions need fixing before merge.

---

## 🔴 High

### 1. `method_exists()` guard removed, so `is_callable()` is always true on Smarty subclasses
**Location:** `dispatch()`, the `$isProcessing && is_callable([$controllerObj, $processMethod])` check and the `is_callable([$controllerObj, $actionMethod])` check.

**Problem:** The deleted comment explained why both checks were needed. Smarty 4 defines `__call`, so `is_callable()` returns `true` for any method name. As a result:
- **Every POST with `process=true` calls `{action}_action_process`, even when it does not exist.** The call goes to Smarty's `__call`, which will throw or misbehave. Many controllers have no `_process` variant, so ordinary form submissions break.
- **The `NotFoundHttpException("Action ... does not exist")` branch is unreachable.** Unknown actions also fall into `__call`.

**Fix:** Restore `method_exists($controllerObj, $method)` in both checks. Ideally, also require the method to be public.

### 2. Action name is no longer sanitized
**Location:** `dispatch()`, the line `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`

**Problem:** The old code applied `preg_replace("/[^A-Za-z0-9_]/", "", ...)` to the action. Now the raw user string is used in two places:
- It is interpolated into a dynamic method name. The `_action` suffix limits what can be called, but any `*_action` / `*_action_process` method on the class or its parents becomes reachable. Combined with #1, arbitrary names also reach `__call`.
- It is stored in `_current_action`. That value is used by `_link()` and templates, which creates a reflected-XSS / header-injection risk.

**Fix:** Validate against `/^[A-Za-z0-9_]+$/` and reject anything else with `BadRequestHttpException`.

### 3. Uncaught Symfony exceptions
**Location:** `dispatch()`, the `BadRequestHttpException` and `NotFoundHttpException` throws.

**Problem:** These replace `echo`/`exit`. Unless `controller.php` and every other caller of `act()` catch `HttpException` and render a proper response, users will see a fatal "Uncaught exception" 500. Depending on `display_errors`, that page may also expose a stack trace and paths.

**Fix:** Either include the caller changes in this PR, or confirm a global handler exists.

---

## 🟠 Medium

### 4. `act()` signature change may fatal on subclass overrides
**Location:** `act(array $qarray): string`

**Problem:** Any `C_*` controller (or module) that overrides `act($qarray)` without matching types will cause a fatal "Declaration must be compatible" error at load time.

**Fix:** Grep for overrides. The same applies to anything implementing the new `ControllerInterface`.

### 5. `process` handling changed in `act()`
**Location:** `act()`, the positional key extraction.

**Problem:** The old code removed `process` from `$qarray` before computing positional keys. Now `$keys[1]` can be `process`. For example, `?practice_settings&process=true&pharmacy&action=edit` now routes to action `process` instead of `pharmacy`.

A related change: the old code keyed off `$_GET['process']`, while the new code keys off `$params['process']`. This differs when callers pass arrays other than `$_GET`.

**Fix:** Strip `process` before computing positional keys.

### 6. Reserved keys in the query string override routing
**Location:** `act()`, the remaining-params loop.

**Problem:** Only `action` is renamed. A query like `?document&retrieve&controller=prescription` overwrites `$params['controller']` and silently routes to a different controller than the positional one. The old behavior passed it as an argument.

**Fix:** Rename or reject `controller` (and similar reserved keys) the same way `action` is handled.

### 7. Arguments are still positional, so "order-independent" is misleading
**Location:** `dispatch()`, the `$args` build and `...array_values($args)` in `$callMethod`.

**Problem:** Arguments are spread positionally in query-string order. With `?controller=document&action=view&doc_id=1&patient_id=2`, the controller receives the arguments in the wrong order. The docblock example implies order doesn't matter.

**Fix:** Either use named arguments (`...$args` with string keys, which works in PHP 8, though unknown keys will error), or correct the documentation.

### 8. `_state` comparison changed from loose to strict
**Location:** `dispatch()`, `$controllerObj->_state === false` (old: `== false`).

**Problem:** Controllers that set `_state` to `0`, `null`, or `""` used to short-circuit after `_process` and now fall through to also run `_action`.

**Fix:** Audit the controllers, or keep the loose comparison.

---

## 🟡 Low

### 9. Whitelist completeness
**Location:** `VALID_CONTROLLERS`

**Problem:** Any `controllers/C_*.class.php` not listed, including ones used by modules or custom code, is now a hard 400.

**Fix:** Verify the list against the `controllers/` directory and all `controller.php?` call sites.

### 10. ACL is applied only to the top-level controller
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`

**Problem:** `pharmacy`, `insurance_company`, `x12_partner`, and others are normally reached via `practice_settings`. They remain directly routable without the `admin/practice` check. This gap existed before the PR, but now that there is an explicit map, it should be closed.

### 11. Empty `$qarray` triggers a warning
**Location:** `act()`, `$keys[0]`

**Problem:** An empty array produces an "Undefined array key" warning before the `BadRequest` is thrown. The `non-empty-array` docblock does not enforce anything at runtime.

### 12. Integer keys break the skip comparison
**Location:** `act()`, the `$key === $controller || $key === $positionalAction` check.

**Problem:** PHP converts numeric-string keys to ints, but `$controller` and `$positionalAction` are cast to string. The strict comparison then fails, so the positional key leaks into the args.

### 13. Non-string return values are silently discarded
**Location:** `dispatch()`, the `$callMethod` closure.

**Problem:** Non-string results are converted to `''`. Actions that return something else (for example, a rendered object or `null` after echoing) lose that value without any signal, which makes debugging harder.

---

**Summary:** Items #1 and #2 are blocking. Restore `method_exists()` and action-name validation, and confirm exception handling at the entry point (#3) before merging.