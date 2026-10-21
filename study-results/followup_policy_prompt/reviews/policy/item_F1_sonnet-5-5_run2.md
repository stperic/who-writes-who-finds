**Review of `Controller::act()` / `dispatch()` refactor**

**1. Action name is no longer sanitized (high, security/correctness)**
- Location: `dispatch()`, `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`
- The old code stripped everything outside `[A-Za-z0-9_]` from the action. The new code builds `"{$action}_action"` from raw user input and calls it dynamically.
- The reachable methods are limited to those with the `_action` suffix, but raw input in a dynamic method name is still unsafe. Restore the sanitization or validate against `/^[A-Za-z0-9_]+$/`.
- The same raw value is echoed into the `NotFoundHttpException` message ("Action '$action' does not exist…"). If an error handler renders that message unescaped, it is reflected XSS. Don't echo user input, or escape it.

**2. `method_exists()` check removed, so the "action not found" path is probably dead (high, correctness)**
- Location: `dispatch()`, the `is_callable([$controllerObj, $actionMethod])` and `is_callable([$controllerObj, $processMethod])` checks.
- The removed code had a comment saying `is_callable()` is always true on Smarty 4 because of `__call`, so `method_exists()` is also required. The new code drops it.
- Consequences:
  - Nonexistent actions are routed into Smarty's `__call` instead of producing a 404.
  - Process methods are always treated as present.
  - Arbitrary user-supplied action names reach Smarty's magic `__call`.
- Restore `method_exists()`.
- In the `$isProcessing ||` branch the action is called unconditionally, with no existence check at all.

**3. `_state` comparison changed from `==` to `===` (medium, behavioral regression)**
- Location: `if ($controllerObj->_state === false)`.
- `_state` is declared without a default, so it is `null`. The old `== false` treated `null`, `0` and `""` as "stop after process". The new strict check falls through and also runs the main action for any controller that doesn't set `_state` to exactly `false`. This can cause double rendering or double side effects.

**4. "Order-independent" routing is not really order-independent (medium, correctness)**
- Location: `$callMethod` uses `...array_values($args)`.
- Remaining params are passed positionally in URL order and their names are discarded. That contradicts the docblock ("order-independent").
- Any extra or unrelated query parameter, such as `csrf_token_form`, shifts the arguments of the action. Passing the array by name with `...$args` would fix the ordering but would need an allow-list.
- Array-valued parameters (`?id[]=1`) are also passed straight into the action and can cause a `TypeError` (500).

**5. `act()` regressions (medium)**
- The old code removed `process` before computing the positional controller and action. The new code reads `array_keys($qarray)` first, so a URL such as `?controller_name&process=true&…` makes `process` the action.
- `$keys[0]` is accessed with no check for an empty array. The `non-empty-array` docblock is not enforced, so an empty query gives an undefined-index warning and then a `BadRequest`.
- The key comparison mixes `int` keys with a string-cast `$controller`, so numeric keys can mismatch.
- Renaming `action` to `sub_action` is a hidden contract change. Sub-controllers that read `$_GET['action']` still work, but they are positionally fed a different arg in the same slot. This is brittle and needs tests.

**6. Controller whitelist may break existing functionality (medium, maintainability)**
- Location: `VALID_CONTROLLERS`.
- The old code loaded any `controllers/C_*.class.php`. Any controller not in the list, including ones in modules or custom installs, now returns 400. Verify the list is complete.
- The whitelist is a security improvement, but the `Hl7` and `X12Partner` mappings and similar entries should be checked against real filenames and class names.

**7. Error handling changed from `echo`+`exit` to exceptions (medium, reliability)**
- Location: `dispatch()`, the `BadRequestHttpException` and `NotFoundHttpException` throws.
- Callers such as `controller.php` and templates may not catch these. Uncaught exceptions can produce blank pages or leak stack traces, depending on the `display_errors` setting. Confirm there is a handler. Also confirm that `symfony/http-kernel` is a direct dependency.

**8. Pre-existing security issue in code this change relies on (medium)**
- Location: process handling in `dispatch()`.
- A GET parameter `process` is converted into `$_POST['process'] = "true"`. This lets a GET request (a link or an image tag) trigger the state-changing `_action_process` handlers, which bypasses POST-only expectations and makes CSRF easier. The change keeps and extends this behavior. Require an actual POST and a CSRF token check.
- ACL coverage is also incomplete. Only `practice_settings` and `prescription` are protected in `CONTROLLER_ACL_MAP`. The other whitelisted controllers (`document`, `insurance_company`, `pharmacy`, `x12_partner`, and so on) rely on their own checks, which should be verified.

**9. Minor**
- `callMethod` silently discards non-string returns (it returns `''`), which hides bugs.
- The `Smarty`/`ControllerInterface` implementation and the new constants have no tests.
- `i_once` still uses `include_once` with an interpolated path. This is safe only because of the whitelist, so keep that dependency documented.