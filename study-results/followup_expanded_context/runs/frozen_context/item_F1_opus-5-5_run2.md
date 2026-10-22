# Review of `Controller::act()` / `dispatch()` refactor

## High severity

### 1. Dropping `method_exists()` breaks dispatch, because `is_callable()` is always true on Smarty subclasses
**Location:** `dispatch()` at `if ($isProcessing && is_callable([$controllerObj, $processMethod]))` and `if ($isProcessing || is_callable([$controllerObj, $actionMethod]))`.

The old code explained the problem in a comment, which this diff deletes: Smarty 4 defines `__call`, so `is_callable()` returns true for any method name on a `Controller`/`Smarty` subclass. The old code paired it with `method_exists()` for that reason. With that check removed:

- **Every POST with `process=true` calls `{action}_action_process`, even when the controller has no such method.**
  - The call falls into Smarty's `__call`.
  - That either throws ("Call of unknown method") or does something unintended.
  - Before, the process step was skipped silently and the normal action ran.
  - This is a functional regression for any controller that has an action without a matching `_process` method.
- **The `NotFoundHttpException("Action ... does not exist")` branch can never run.**
  - Unknown actions are sent to `__call` instead of producing a clean 404.

**Fix:** Restore `method_exists($controllerObj, $method)`. Ideally, also check that the method is public, for example with `ReflectionMethod`.

### 2. Action name is no longer sanitized or validated
**Location:** `dispatch()` at `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`

The old code removed non-`[A-Za-z0-9_]` characters from the action. Now the request supplies the action, and it is used directly to build a method name, which is then invoked dynamically. Combined with issue #1, an attacker can send arbitrary method names into Smarty's magic `__call`. That handler interprets `get*`/`set*`-style names as property accessors.

- The `_action` suffix limits the attack surface but does not remove it.
- Request input should never select arbitrary methods without validation.

**Fix:**
- Validate with `preg_match('/^[A-Za-z0-9_]+$/', $action)`. Reject anything else with `BadRequestHttpException`.
- Treat an empty string as `default`. Today `action=` produces a call to `_action`, whereas the old code fell back to `default`.

## Medium severity

### 3. `dispatch()` is not actually order-independent
**Location:** `dispatch()` docblock, `$args[$key] = ...`, and `$controllerObj->$method(...array_values($args))`.

The docblock promises order-independent routing, for example `controller=document&action=view&patient_id=123&doc_id=456`. However:

- The arguments are collected by name, then flattened with `array_values()`.
- They are passed positionally in query-string order.
- `...&doc_id=456&patient_id=123` would therefore swap the arguments silently.

This is a data-integrity hazard in a medical record context: a document could be shown or edited for the wrong patient.

**Fix:** Do one of the following:
- Map arguments to parameters by name. With PHP 8 you can spread a string-keyed array as named arguments, but only if the parameter names match. Otherwise use Reflection.
- Or explicitly document that order still matters.

### 4. The `process` flag is no longer removed before positional parsing in `act()`
**Location:** `act()` at `$keys = array_keys($qarray); ... $positionalAction = (string) ($keys[1] ?? 'default');`

The old code ran `unset($qarray['process'])` before reading the controller and action keys. The new `act()` reads them first, and `process` is only stripped later, inside `dispatch()`.

- A legacy URL such as `controller.php?practice_settings&process=true&pharmacy...` would now resolve the action as `process`.
- That produces calls to `process_action` / `process_action_process`, which is a behavior change.

**Fix:** Strip `process` in `act()` before computing `$keys`.

### 5. Errors are now uncaught Symfony HTTP exceptions
**Location:** the `BadRequestHttpException` and `NotFoundHttpException` throws.

- Previously the code echoed a message and called `exit`.
- Unless `controller.php` and the nested callers (such as `C_PracticeSettings::*_action`) catch these and convert them to responses, users will get 500 errors or uncaught-exception pages.
- Depending on display settings, those pages may leak stack traces.

**Fix:** Confirm that a handler exists for these exceptions, or add one.

## Low severity

### 6. `_state` comparison tightened
**Location:** `if ($controllerObj->_state === false)`

- The old check was `== false`.
- Any controller whose process method sets `_state` to `0`, `null`, or `''` will no longer short-circuit.
- Please verify that all `_process` methods assign a strict `false`.

### 7. Empty-value handling is subtly different
**Location:** `$args[$key] = $value === '' ? null : $value;`

- The old code also converted `null`, empty arrays, and other `empty()` values (except `"0"`) to `null`.
- The new code converts only `''`.
- This is probably fine, but it is a behavior change; the comment says "matching act() behavior".

### 8. `act()` uses `$keys[0]` without a guard
**Location:** `act()` at `$controller = (string) $keys[0];`

- An empty `$_GET` emits an undefined-index warning before `BadRequestHttpException` is thrown.
- The `non-empty-array` PHPDoc does not enforce this at runtime.
- **Fix:** Add an explicit `if ($qarray === [])` check.

### 9. Strict key comparison against string-cast keys in `act()`
**Location:** `if ($key === $controller || $key === $positionalAction)`

- `$controller` and `$positionalAction` are cast to strings, but PHP turns numeric array keys into ints.
- A numeric second key such as `?document&123` would not be excluded from the arguments and would be passed twice.
- **Fix:** Use `(string) $key ===`.

### 10. Backward-compatibility of the `act()` signature
**Location:** `act(array $qarray): string`

- Adding parameter and return types breaks any subclass that overrides `act()` without matching types.
- Please check that no controllers or modules do this.

### 11. Duplicated ACL logic (maintainability)
- `C_PracticeSettings::__construct` still runs its own `admin/practice` check, which duplicates `CONTROLLER_ACL_MAP`.
- This is harmless today, but the two copies could drift apart.
- Nested dispatches, such as `practice_settings` → `pharmacy`, rely on the outer controller's ACL because sub-controllers have no map entry. This matches the old behavior, but it is worth stating explicitly in the map's docblock.