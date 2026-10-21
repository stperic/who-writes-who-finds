## Review: `Controller::dispatch()` and the `act()` refactor

The refactor adds a whitelist, centralizes ACL checks, and replaces `echo`/`exit` with exceptions. It also introduces several correctness regressions, the most serious being that the new routing does not actually match the parameters to method names.

### Issues

**1. Arguments are passed positionally, so "order-independent routing" is broken (High)**
Location: `dispatch()`, the `$callMethod` closure: `$controllerObj->$method(...array_values($args));`

The `$args` array is keyed by parameter name (`patient_id`, `doc_id`, ...), but the keys are discarded with `array_values()`. The arguments are then passed in the order they appear in the query string. The docblock promises that `controller=document&action=view&patient_id=123&doc_id=456` works regardless of order, but `doc_id=456&patient_id=123` would silently pass the values to the wrong parameters. Missing optional parameters also shift every later argument. Either bind by name (reflection on the target method, mapping to its parameter names) or document and enforce a fixed order.

**2. `is_callable()` alone is unreliable here; the original `method_exists()` check was dropped (High)**
Location: `$isProcessing && is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])`

The removed code had an explicit comment: since Smarty 4 `__call` makes `is_callable()` always return true, `method_exists()` must also be checked. This diff removes that check. Consequently:
- For an unknown action, `is_callable` returns true via `Smarty::__call`, so the `NotFoundHttpException` branch is never reached and the call goes into Smarty's magic method instead.
- The `else` branch's "action does not exist" error is effectively dead code.

Restore `method_exists()` alongside `is_callable()`, or use `method_exists()` only.

**3. Early-return condition changed from `== false` to `=== false` (Medium)**
Location: `if ($controllerObj->_state === false)`

The original used `== false`, so a `null` `_state` also short-circuited and returned the process output. With `===`, `null` now continues into the action method, which is a silent behavior change for controllers that leave `_state` unset. Restore the loose comparison or confirm that all controllers set `_state` to a boolean.

**4. Hard failures replace `echo` + `exit` without verifying callers (Medium)**
Location: all `throw` sites (`BadRequestHttpException`, `NotFoundHttpException`)

Previously an unknown controller or action produced readable output and terminated. Now an uncaught exception is thrown. Unless the entry point (`controller.php` or equivalent) catches these exceptions and renders an appropriate response, users will get a 500 error page or a fatal error. Confirm the caller handles these types.

**5. Action name is no longer sanitized (Medium)**
Location: `$action = is_string($params['action'] ?? null) ? ...; $actionMethod = "{$action}_action";`

The original code applied `preg_replace("/[^A-Za-z0-9_]/", "", ...)` to the controller and action names. The new code accepts any string. Combined with the `__call` issue in #2, arbitrary strings can reach dynamic method dispatch. Re-add the character-whitelist sanitization, or validate against `/^[A-Za-z0-9_]+$/`.

**6. `act()` assumes a non-empty array (Low)**
Location: `$keys = array_keys($qarray); $controller = (string) $keys[0];`

The signature documents `non-empty-array`, but nothing enforces it. An empty array produces an undefined-offset warning and routes to an empty controller name, which is then rejected with a less helpful message. Add an explicit guard.

**7. `process` handling reads `$_GET` but routes from `$params` (Low)**
Location: `unset($_GET['process']);` inside `dispatch()`

`dispatch()` accepts an arbitrary `$params` array, but it unsets from `$_GET` while removing `process` from `$params`. If a caller passes a different array, the two diverge. Make the code consistent (e.g., only operate on `$params`, and set `$_POST['process']` explicitly).

**8. Missing-argument semantics changed (Low)**
Location: the args loop

Previously, declared-but-absent query arguments were passed as `null`. Now absent arguments are simply omitted, so PHP will raise `ArgumentCountError` for required parameters, or shift subsequent positional arguments (see #1). Also, the empty-to-null rule now only covers `''`, whereas the old code also normalized other falsy values. Confirm this is intentional.

**9. Legacy `act()` is marked `@deprecated` but has no migration or tests (Low / Maintainability)**
No caller updates or tests accompany the change, which makes regressions in #1–#3 likely to slip through. Add tests for: positional routing via `act()`, unknown controller, unknown action, ACL denial, and the `process` POST flow.

### Summary

The most important fixes before merge are #1 (argument binding), #2 (restore `method_exists()`), and #5 (action-name sanitization). #3 and #4 are behavior changes that need either a restored comparison or explicit confirmation from the caller. I would not approve this as-is.