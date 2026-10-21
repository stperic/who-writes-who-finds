**Review of the `Controller::act()` / `dispatch()` refactor**

**1. High: the "action does not exist" check is now ineffective, and `method_exists()` was removed**
- Location: `dispatch()`, the `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])` checks.
- The removed code had a comment saying that `is_callable()` is always true because Smarty 4's `__call` intercepts everything, so it also required `method_exists()`. This diff drops `method_exists()`.
- A nonexistent action will now be "callable" and be routed into Smarty's `__call`. That throws an unrelated `BadMethodCallException` or `SmartyException`, which means a 500 instead of the intended 404. The `NotFoundHttpException` branch becomes dead code.
- The same applies to `*_action_process`. A nonexistent process method is treated as callable and invoked.
- The condition `$isProcessing || is_callable(...)` runs the action method even when it doesn't exist, whenever `process=true` is set.
- Fix: restore `method_exists()` alongside `is_callable()`, and drop the `$isProcessing ||` short-circuit.

**2. Medium: the action name is no longer sanitized**
- Location: `dispatch()`, where `$action` is built from `$params['action']`.
- The old code stripped everything outside `[A-Za-z0-9_]` from both the controller and the action. The controller is now whitelisted, but the action goes straight into `"{$action}_action"` as a dynamic method name.
- Callers are limited to methods ending in `_action` or `_action_process`, but that is still arbitrary input choosing the method. Combined with issue 1, it reaches Smarty magic.
- Fix: re-apply the regex, or validate with `/^[A-Za-z0-9_]+$/`.

**3. Medium: error handling moved from `echo`/`exit` to exceptions, with no visible handler**
- Location: the `BadRequestHttpException` and `NotFoundHttpException` throws.
- The legacy entry point (`controller.php`) is not in this diff. If it does not catch these exceptions, users get an uncaught fatal error or stack trace instead of a clean message.
- The `NotFoundHttpException` message embeds the raw user-supplied `$action`. If any handler renders that message as HTML, it is a reflected XSS. Either sanitize it or confirm that the handler escapes it.
- Please confirm callers handle these exceptions.

**4. Medium: the whitelist may break existing controllers**
- Location: `VALID_CONTROLLERS`.
- The old code loaded any `controllers/C_*.class.php` file. A hard-coded list will silently break any controller that is missing from it, such as a module or custom controller, or any added later.
- It also duplicates knowledge of the `controllers/` directory. Verify the list against that directory.

**5. Medium: subtle behavior changes in argument and state handling**
- `$controllerObj->_state === false` was previously `== false`. A controller that sets `_state` to `0` or `null` no longer short-circuits after the process step.
- The old code turned empty values into `null` except `"0"`. The new code only maps `''` to `null`, so empty arrays and other falsy values now behave differently.
- `callMethod` returns `''` for any non-string result. A controller that returns something else has its output silently dropped, where the old `.=` would have stringified it.
- In `act()`, `$key === $controller` compares strictly. An integer array key never equals the string-cast name, so numeric keys can be mishandled.

**6. Low: misleading docs and a half-finished migration**
- `dispatch()` is documented as "order-independent routing", but extra arguments are still passed positionally via `array_values($args)` in URL order. Parameter names are ignored, so reordering query params still changes behavior.
- The `act()` rename of `action` to `sub_action` is subtle. It only works if the `$_GET`/positional delegation in sub-controllers like `practice_settings` was verified. There is no test coverage in the diff for this, nor for ACL, process flow, or the error paths.
- `act()` is marked `@deprecated` but is still the primary entry point.

**7. Low: ACL map duplication**
- `CONTROLLER_ACL_MAP` and `VALID_CONTROLLERS` are separate constants that must be kept in sync.
- `xl($displayName)` on a variable defeats translation string extraction.

**Summary:** Issue 1 is a regression that should block the merge. Issues 2–5 should be addressed or explicitly confirmed before merging.