## Review findings

**1. High: the `method_exists()` guard was dropped, so missing actions are no longer detected.**
- Location: `dispatch()`, the `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])` checks.
- The removed code said `is_callable()` is always true on Smarty 4 because of `__call`, so a `method_exists()` check is also required. The new code uses only `is_callable()`.
- The `NotFoundHttpException("Action ... does not exist")` branch is effectively unreachable. An unknown action falls into Smarty's `__call`, which throws a `SmartyException` or behaves unpredictably.
- On a POST with `process=true`, every action that has no `_action_process` method now goes through `__call` for the process method. This is likely to break existing forms.
- Fix: restore `method_exists() && is_callable()` for both the process and the action method.

**2. High: the action name is no longer sanitized.**
- Location: `dispatch()`, `$action = $params['action']`.
- The old code stripped everything outside `[A-Za-z0-9_]`. The new code builds a method name straight from user input and calls it dynamically.
- The `_action` suffix limits what can be called, but this is still an unvalidated dynamic call.
- Validate the action with `^[A-Za-z0-9_]+$`, and use `method_exists` as well.
- An empty `action` (for example `action=`) now yields the method `_action` instead of falling back to `default`, which is a regression. Use `=== ''` to fall back to `'default'`.

**3. Medium: the user-controlled action is reflected in exception messages.**
- Location: `NotFoundHttpException("Action '$action' does not exist...")`.
- If the error handler renders the message as HTML without escaping, this is reflected XSS. The old code echoed only the sanitized value.
- Callers of `act()` previously relied on `echo` and `exit`. Please verify that they, or a kernel listener, now handle these exceptions. Otherwise users get uncaught exceptions and possible stack-trace disclosure.

**4. Medium: `act()` mis-parses `process` when it is the first or second key.**
- The old code removed `process` from `$qarray` before deriving the controller and action. The new `act()` derives `$keys[0]` and `$keys[1]` first.
- A URL like `?document&process=true&...` therefore treats `process` as the action.
- `act()` also reads `$keys[0]` on a possibly empty array, which gives an undefined-offset warning despite the `non-empty-array` docblock. The `array` type does not enforce that.

**5. Medium: parameter collisions in `act()`.**
- Extra query params named `controller` or `sub_action` overwrite the routing keys in `$params`. For example, `?practice_settings&list&controller=document` reroutes the request.
- The ACL check does use the final controller, so this is not an ACL bypass, but it is unexpected routing control.
- Reserved keys should be filtered or rejected.

**6. Medium: argument passing is still positional, and it is also changed.**
- `array_values($args)` passes every non-reserved query param positionally in URL order.
- So `dispatch()` is not order-independent, as its docblock claims. Reordering params, or extra params such as `csrf_token_form` or `sub_action`, shifts the arguments.
- The old code used only the keys after the action. Now all extra params are passed, and `sub_action` is injected into the argument list.
- Array values can reach typed parameters and cause a `TypeError`.
- The old "empty but not `"0"` becomes null" logic is replaced by `=== ''` only. Behavior differs for other empty values such as null.

**7. Low: int-versus-string key comparison in `act()`.**
- `$key === $controller` and `$key === $positionalAction` compare against string-cast values. PHP converts numeric string keys to int, so a numeric action key is not skipped and is passed as an argument.

**8. Low: loose comparison tightened to strict.**
- `$controllerObj->_state === false` replaces `== false`. Controllers that set `_state` to `0` or `null` no longer short-circuit after the process step.

**9. Low: non-string action results are silently discarded.**
- `$callMethod` returns `''` for non-string results, where the old code concatenated them. This can hide bugs.

**10. Pre-existing security issue the change still relies on: `process` can be set via GET.**
- `isset($params['process'])` from `$_GET` sets `$_POST['process'] = "true"`. State-changing `_action_process` handlers can therefore be triggered with a GET request, which is a CSRF-style risk.
- Controllers should verify CSRF tokens and the request method. This change should not carry that behavior forward.

**11. Low: ACL coverage.**
- Only `practice_settings` and `prescription` have ACL entries. Controllers such as `document`, `insurance_company`, `x12_partner`, and `hl7` have no central check, so protection depends on each controller.
- The new whitelist also removes any controller not listed, which could break plugins or custom controllers.

**12. Maintainability: no tests.**
- Routing, ACL, and process semantics changed substantially, and the diff includes no tests.
- `ControllerInterface` is not shown in the diff. Please confirm that it exists and that the method signatures match.