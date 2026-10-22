# Review: `Controller::act()` / `dispatch()` refactor

## High

**1. Smarty `__call` makes the action-existence check ineffective, and the action name is no longer sanitized**
- **Where:** `dispatch()`, the `is_callable([$controllerObj, $actionMethod])` and `is_callable([$controllerObj, $processMethod])` checks.
- **Problem:** The removed comment explained why the old code also used `method_exists()`: Smarty 4's `__call` makes `is_callable()` always return `true`. The new code drops `method_exists()`, so:
  - Any `action` value (and any `*_action_process` name) is treated as callable.
  - The `NotFoundHttpException("Action ... does not exist")` branch can never be reached.
  - Unknown actions now go through Smarty's `__call`, which throws its own error or behaves unpredictably.
  - A process method that doesn't exist will be "called" whenever `process=true`.
- **Sanitization regression:** The old code stripped `$c_action` to `[A-Za-z0-9_]`. Now `$params['action']` comes straight from `$_GET` and is interpolated into a method name.
- **Fix:**
  - Restore the `method_exists()` checks.
  - Validate `action` against `/^[A-Za-z0-9_]+$/` and reject anything else with `BadRequestHttpException`.

**2. Possible reflected XSS / information disclosure in exception messages**
- **Where:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className")`.
- **Problem:**
  - `$action` is raw user input. If the error handler (or dev/debug mode) renders exception messages as HTML, this is reflected XSS. The old code only echoed the sanitized value.
  - `controller.php` must also catch `HttpException`s. Otherwise these become uncaught fatals that may expose stack traces and filesystem paths, rather than the previous plain message.
- **Fix:**
  - Don't include unsanitized input in the message, or escape it.
  - Make sure the front controller converts `HttpException` into a proper 400/404 response.

## Medium

**3. `process` is no longer removed before positional parsing in `act()`**
- **Where:** `act()`.
- **Problem:** The old code removed `process` from `$qarray` before computing the controller and action keys. Now `process` stays in `$qarray` while `$keys[1]` is computed. A URL like `?document&process=true&upload&...` will resolve the action to `process`, so it calls `process_action` instead of `upload_action`.
- **Fix:** Unset `process` from `$qarray` (when present) before calling `array_keys`.

**4. Query parameters named `controller`, `action`, or `sub_action` collide with routing**
- **Where:** `act()`, the loop that copies remaining params into `$params`.
- **Problem:**
  - A later key literally named `controller` overwrites `$params['controller']`. For example, `?pharmacy&list&controller=x12_partner` routes to a different controller than the URL's positional controller.
  - An existing `sub_action` key is silently overwritten by the rename of `action`.
- **Severity note:** ACL still follows the final controller, so this is mostly a correctness and maintainability issue rather than a bypass.
- **Fix:** Explicitly skip or reject the reserved keys in `act()`.

**5. The controller whitelist may break existing routes**
- **Where:** `VALID_CONTROLLERS`.
- **Problem:** Previously any `controllers/C_*.class.php` file could be routed to. Any controller or URL not in the hardcoded list (including third-party or module links) now gets a 400.
- **Fix:** Verify every file in `controllers/` and every `controller.php?...` link in the codebase is covered, or document the intentional removal.

## Low

**6. Integer query keys bypass the skip check in `act()`**
- **Where:** `act()`, `$key === $controller || $key === $positionalAction`.
- **Problem:** `$controller` and `$positionalAction` are cast to string, but PHP turns numeric query keys into `int`. A numeric first or second key (e.g. `?123&...`) fails the strict comparison and is passed through as an argument.
- **Fix:** Compare `(string) $key`.

**7. Empty-value semantics changed**
- **Where:** `dispatch()`, the argument-building loop.
- **Problem:** The old code passed `null` for any `empty()` value except `"0"`, which included empty arrays and `null`. The new code only converts `''`. The comment "matching act() behavior" is therefore inaccurate. Empty arrays (e.g. `foo[]=`) will now be passed as arrays.

**8. Unguarded `$keys[0]` on empty input**
- **Where:** `act()`.
- **Problem:** `$keys[0]` is undefined if `$qarray` is empty. The PHPDoc says `non-empty-array`, but there is no runtime guard, so this produces a warning plus a generic 400.

**9. ACL checks are now duplicated**
- **Where:** `CONTROLLER_ACL_MAP` and `C_PracticeSettings::__construct`.
- **Problem:** `C_PracticeSettings` still performs its own `admin/practice` check, so the same rule now lives in two places. This is harmless, but they can drift apart. Consider documenting which location is authoritative.

**10. Positional argument passing is fragile**
- **Where:** `dispatch()`, `array_values($args)`.
- **Problem:** Arguments are passed by position in query-string order, not by name. Any reordering of URL parameters (which `dispatch()` claims to make order-independent) silently changes which value lands in which method parameter.
- **Fix:** Document this clearly, or move to named arguments.