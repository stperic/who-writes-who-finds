# PR Review: `Controller::act()` → `dispatch()` refactor

The whitelist is a real hardening improvement over loading controller files from user input. However, the refactor drops a safeguard that was there on purpose and changes routing behavior in several ways that will break existing URLs.

---

## 🔴 High

### 1. `method_exists()` checks removed; `is_callable()` is always true on Smarty subclasses
**Location:** `dispatch()`, the `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])` checks.

**Problem:** The deleted comment explained why both checks existed: Smarty 4 defines `__call`, so `is_callable()` returns `true` for any method name on a `Controller`/Smarty subclass. As a result:

- **Process path:** Any request with `process=true` will call `{$action}_action_process` even when the controller doesn't define it. That call goes into Smarty's `__call`, which typically throws `SmartyException` (unknown method). Before, the process step was skipped and the normal action ran. This breaks every form POST to an action that has no `_process` handler.
- **Normal path:** The `else` branch that throws `NotFoundHttpException` is effectively dead. Unknown actions fall into Smarty's `__call` and produce a 500 (or whatever Smarty's magic does), not a 404.

**Fix:** Restore the `method_exists($controllerObj, $method)` check alongside `is_callable` in both places, or use `method_exists` alone.

### 2. Action name is no longer sanitized before dynamic method dispatch
**Location:** `dispatch()`, `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`

**Problem:** The old code ran `preg_replace("/[^A-Za-z0-9_]/", "", ...)` on the action. Now the raw user string is used in several places:

- It is interpolated into a method name. Combined with issue #1, arbitrary names reach Smarty's `__call`, whose extension handler has magic behavior for some name patterns.
- It is assigned to `_current_action`, which `_link()` and templates use to build URLs. That is a potential reflected-XSS or URL-injection vector.
- It is reflected verbatim in the exception message. If exceptions are rendered to the user, that is XSS.

**Fix:** Validate with `preg_match('/^[A-Za-z0-9_]+$/', $action)` and reject anything else with `BadRequestHttpException`. Rejecting is better than silently stripping characters.

---

## 🟠 Medium

### 3. `process` as the second positional key is misread as the action
**Location:** `act()`, `$positionalAction = (string) ($keys[1] ?? 'default');`

**Problem:** The old code removed `process` from `$qarray` *before* computing positional keys. The new code computes positions first.

- For URLs like `?practice_settings&process=true&...`, the action becomes `"process"`.
- The loop then skips the `process` key, because it matches `$positionalAction`.
- So the process flag never reaches `dispatch()`, `$_POST['process']` is never set, and `process_action()` is invoked instead.

**Fix:** Strip `process` from `$qarray` (and remember it) before extracting positional keys.

### 4. Query params named `controller` or `sub_action` overwrite routing values
**Location:** `act()`, `$params[$key === 'action' ? 'sub_action' : $key] = $value;`

**Problem:**
- A non-positional param literally named `controller` (e.g. `?document&view&controller=pharmacy`) overwrites `$params['controller']`. That silently reroutes the request to a different controller than the positional one. The ACL check follows the final value, so this is not a direct ACL bypass, but it is confusing and a routing-hijack vector.
- `sub_action` can be clobbered in the same way.

**Fix:** Skip or reject reserved keys (`controller`, `sub_action`, `process`) in the remaining-params loop, or namespace them.

### 5. Signature change on public `act()` may fatal in subclasses
**Location:** `public function act(array $qarray): string`

**Problem:** Adding parameter and return types to a public method is a BC break. Any subclass or module that overrides `act($qarray)` without matching types will fatal with "Declaration must be compatible". Callers that rely on `act()` returning non-string output will also break.

**Fix:** Grep `controllers/`, `interface/`, and custom modules for overrides. Also confirm `ControllerInterface` declares compatible signatures.

### 6. Error handling changed from echo + exit to uncaught Symfony exceptions
**Location:** `dispatch()`, the `throw new BadRequestHttpException` and `throw new NotFoundHttpException` calls.

**Problem:** It is unclear that `controller.php` and other `act()` callers wrap this in a handler that converts `HttpException` into an HTTP status. If they don't:
- users get a 500 and possibly a stack trace (information disclosure), and
- issue #1 makes these exceptions much more likely to occur.

**Fix:** Verify the entry points catch `HttpExceptionInterface`, or add a handler.

### 7. Whitelist codifies direct access to controllers that have no ACL
**Location:** `VALID_CONTROLLERS` and `CONTROLLER_ACL_MAP`.

**Problem:** `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, and `document_category` are normally reached through `practice_settings`, which requires `admin/practice`. They are directly routable with no ACL check. This was true before, but this PR is the natural place to close it since an ACL map now exists.

**Fix:** Add ACL entries for these (e.g. `admin/practice`). For `document`, `hl7`, and `patient_finder`, confirm whether a check exists elsewhere.

---

## 🟡 Low

### 8. `_state` comparison changed from loose to strict
**Location:** `if ($controllerObj->_state === false)`

**Problem:** The old code used `== false`. Controllers that set `_state` to `0`, `null`, or `''` to stop processing will now fall through and also run the display action.

**Fix:** Either keep the loose comparison or audit the controllers.

### 9. Empty-value normalization narrowed
**Location:** `$args[$key] = $value === '' ? null : $value;`

**Problem:** The old code converted any `empty()` value except `"0"` to `null`, which includes empty arrays (e.g. `foo[]=` patterns). Empty arrays now stay `[]`, so action method signatures that expect `null` may behave differently.

### 10. Integer and numeric keys break skip logic in `act()`
**Location:** `act()`, `$key === $controller || $key === $positionalAction`.

**Problem:** PHP turns numeric-string keys into ints. The `(string)` casts then make the strict comparisons fail, so a numeric positional key would be duplicated into the args.

**Fix:** Compare by position (e.g. `array_slice($qarray, 2, null, true)`) instead of by key value.

### 11. Unguarded `$keys[0]` on empty input
**Location:** `act()`, `$keys[0]`.

**Problem:** An empty `$qarray` raises an "undefined array key" warning before reaching the BadRequest path. The `non-empty-array` docblock is not enforced at runtime.

### 12. Non-string action results silently discarded
**Location:** the `$callMethod` closure.

**Problem:** Previously, `.=` coerced the action's result to a string (ints, `Stringable` objects). Now anything that isn't a string becomes `''`. This is probably fine but is an undocumented behavior change.

### 13. Whitelist completeness and case sensitivity
**Location:** `VALID_CONTROLLERS`

**Problem:**
- Please verify the list covers every `controllers/C_*.class.php` file and every `controller.php?<name>` link in the codebase (grep for `controller.php?`).
- The old routing accepted variants like `Practice_Settings`; the whitelist is case-sensitive. Bookmarked or legacy links may now get a 400.

---

## Summary

| # | Issue | Severity |
|---|---|---|
| 1 | `method_exists` removed; Smarty `__call` makes `is_callable` always true | High |
| 2 | Action name unsanitized (method dispatch, `_current_action`, error message) | High |
| 3 | `process` as second key becomes the action | Medium |
| 4 | Params named `controller` / `sub_action` overwrite routing | Medium |
| 5 | Typed `act()` signature breaks overrides | Medium |
| 6 | Exceptions may be unhandled, giving 500s or leaking traces | Medium |
| 7 | Sub-controllers directly routable without ACL | Medium |
| 8–13 | Behavioral edge cases (`_state`, empty values, numeric keys, empty input, return coercion, whitelist coverage) | Low |

I'd block the merge on #1 and #2. #3 and #5 also need to be addressed or confirmed before merging.