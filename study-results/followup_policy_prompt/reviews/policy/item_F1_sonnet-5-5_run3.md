## Review findings

### High

1. **`is_callable()` without `method_exists()` breaks dispatch (`dispatch()`).**
   - The old code had a comment explaining that Smarty 4's `__call` makes `is_callable()` always true, so both checks were needed. The new code removes that comment and the `method_exists()` check.
   - **Process path:** `$isProcessing && is_callable([$controllerObj, $processMethod])` is now true even when no `*_action_process` method exists. The call falls into Smarty's `__call` and throws `SmartyException` (undefined method) instead of skipping to the plain action.
   - **Missing-action path:** `is_callable([$controllerObj, $actionMethod])` is always true, so the `NotFoundHttpException` branch is effectively dead. The `else` can never run for a missing action, and the failure surfaces as an obscure Smarty exception or fatal.
   - **Fix:** restore `method_exists()` alongside `is_callable()`.

2. **The action name is no longer sanitized, and it is used unsanitized elsewhere.**
   - The old code stripped everything outside `[A-Za-z0-9_]` from the controller and action. The new code uses `$params['action']` raw in `"{$action}_action"` and stores it in `$controllerObj->_current_action`.
   - `_current_action` is consumed by templates and `_link()`, so this opens a possible reflected XSS or injection if it is echoed.
   - The raw value is also interpolated into the `NotFoundHttpException` message. If the error handler renders that message as HTML, that is another XSS vector.
   - Callable-string tricks such as `parent::x` are partially possible through `is_callable` with array callables.
   - **Fix:** validate the action against `/^[A-Za-z0-9_]+$/` (ideally an allowlist) and escape it in messages.

### Medium

3. **Strictness change in `_state` check.** The old code used `$c_obj->_state == false`, which also matched `null` and `0`. The new code uses `=== false`. Controllers that leave `_state` unset or null previously returned early after the process action and now fall through to run the main action as well. This is a silent behavior change that could cause double execution of state-changing actions.

4. **Arguments are still positional, contradicting the "order-independent" claim.**
   - `$controllerObj->$method(...array_values($args))` binds by URL parameter order, not by name. The docblock and deprecation note imply names matter, but reordering or adding extra query params shifts arguments into the wrong parameters.
   - Attacker-supplied extra parameters can displace legitimate ones.
   - Array values (`foo[]=x`) can reach typed parameters and cause `TypeError`s, which is a reliability and DoS concern.
   - **Fix:** bind by parameter name via reflection, or use named arguments with filtering.

5. **GET can trigger process mode (pre-existing, but this code touches it).** `$params['process']` from the query string sets `$_POST['process'] = "true"`. State-changing `*_action_process` handlers can therefore be invoked via a GET request, which bypasses POST-only assumptions and weakens CSRF defenses. There is also no CSRF check in the dispatcher. Process mode should require a real POST request and a CSRF token.

6. **Hard-coded controller whitelist.** The list can drift from `/controllers`, and any controller not listed (including module or custom ones) is now unreachable with a 400 error. Please verify that every `C_*.class.php` file is covered.

7. **Behavior change from `echo`/`exit` to exceptions.** Callers such as `controller.php` must now catch `BadRequestHttpException` and `NotFoundHttpException`. The diff does not show this, so uncaught exceptions would produce a fatal error or stack trace disclosure. Please confirm that callers handle them.

8. **ACL coverage is minimal (pre-existing).** Only `practice_settings` and `prescription` have central ACL checks. The other whitelisted controllers (`document`, `pharmacy`, `insurance_company`, `x12_partner`, `hl7`, `patient_finder`, …) rely entirely on their own checks, so a missing check in any of them is directly reachable. Consider a default-deny ACL map.

### Low

9. **`act()` edge cases.**
   - `$keys[0]` is read without an emptiness check. The `non-empty-array` docblock is not enforced, so an empty array causes an undefined offset.
   - The `$key === $controller` comparison is strict, but `array_keys` can return ints (e.g. numeric keys) while `$controller` is cast to string, so those keys won't be skipped.
   - If a user passes a literal `controller=` param, it may collide with the routing keys.
   - The `action` → `sub_action` rename changes what is passed positionally and only works if downstream code expects it.

10. **Output coercion.** `is_string($result) ? $result : ''` silently discards non-string returns (ints, Stringable objects). This could hide bugs.

11. **Empty-string normalization.** `$value === ''` becomes `null`, but the old code also treated other empty values (`empty()`) as null while preserving `"0"`. This subtle difference should be documented or tested.

12. **Missing tests.** There are none for the new routing, whitelist, ACL map, or process flow. Tests for these would have caught finding 1.