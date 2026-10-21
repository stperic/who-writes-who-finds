# Code Review: `Controller::act()` / `dispatch()` refactor

The controller whitelist is a real improvement over building a class name from user input. However, the refactor drops several safety checks the old code had, and it changes behavior in ways existing URLs may depend on.

---

## High

### 1. `method_exists()` guard removed, so arbitrary method names reach Smarty's `__call`
**Location:** `dispatch()`, both `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])`

The removed comment explained why the old code needed both checks: Smarty 4 defines `__call`, so `is_callable()` is **always true** on any `Controller`. The new code relies on `is_callable()` alone. As a result:

- **Process method:** Any request with `process` set always calls `{$action}_action_process`, even when that method does not exist. Smarty's `__call` handles it, and depending on the name, Smarty may interpret it as a getter/setter or extension call.
- **Action method:** `is_callable([$controllerObj, $actionMethod])` is always true. The `NotFoundHttpException` branch is dead code, and every unknown action goes to `__call`.

Combined with issue 2, this lets a user choose the method name that Smarty's magic dispatcher receives.

**Fix:** Restore `method_exists($controllerObj, $method)`, ideally together with a check that the method is public and declared on the `C_*` class.

### 2. Action name is no longer sanitized
**Location:** `dispatch()`: `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`

- The old code applied `preg_replace("/[^A-Za-z0-9_]/", "", ...)` to the action. The new code uses the raw user string in two places:
  - the dynamic method name `$controllerObj->$method(...)`;
  - `_current_action`, which templates and `_link()` may echo or use to build URLs.
- **Fix:** Validate against `/^[A-Za-z0-9_]+$/` and reject anything else with a 400.

### 3. Reflected XSS / information leak through exception messages
**Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`

- `$action` is unsanitized user input placed into an exception message.
- If `controller.php` (or a global handler) does not catch `HttpException`, PHP's uncaught-exception output shows the message. With `display_errors` on, this is reflected XSS, and the stack trace also leaks file paths.
- The old code echoed only the sanitized action.
- **Fix:**
  - Sanitize or validate the action first (issue 2).
  - Make sure callers catch these exceptions and render escaped, generic error pages.
  - Check that the entry point actually handles `BadRequestHttpException` / `NotFoundHttpException`. Otherwise every bad URL becomes a fatal error and a 500.

---

## Medium

### 4. `_state` comparison changed from `== false` to `=== false`
**Location:** `if ($controllerObj->_state === false)`

- `public $_state;` defaults to `null`. Under the old loose comparison, `null == false` held, so after a `*_action_process` call the method returned early unless the controller explicitly set `_state = true`.
- Now `null` (or `0`, or `''`) falls through and also runs the view action.
- This can cause double rendering or re-running logic after processing.
- **Fix:** Either keep the loose semantics or audit every `C_*` controller to confirm it sets `_state` explicitly.

### 5. Legacy `?controller&process&...` URLs now break
**Location:** `act()`

- The old code removed `process` from `$qarray` **before** taking the second key as the action.
- Now `$keys[1]` is read first. A URL like `controller.php?practice_settings&process&pharmacy&action=list` resolves the action to `process`, which leads to calling `process_action`.
- **Fix:** Strip `process` from `$qarray` before extracting the positional keys.

### 6. Legacy query keys can override routing parameters
**Location:** `act()` foreach loop

- `$params['controller']` and `$params['action']` are set first, but the loop only renames `action`.
- A `controller` key later in the query string overwrites the routing controller. Example: `?document&view&controller=prescription`.
- The whitelist and ACL still apply to the new value, but routing no longer matches what the positional URL says. That is confusing and could defeat an upstream check that looked only at the first key.
- **Fix:** Rename or reject `controller` the same way `action` is handled.

### 7. Argument passing is still order-dependent, and new keys are included
**Location:** `dispatch()`: `$controllerObj->$method(...array_values($args))`

- The docblock promises "order-independent routing," but arguments are still bound by position in the query string. `?controller=document&action=view&doc_id=1&patient_id=2` would swap the parameters.
- `act()` also now injects `sub_action` into the argument list at the position where `action=` appeared. This may shift arguments compared with the old behavior, where `action` was simply another positional arg value.
- **Fix:** Bind by name using `ReflectionMethod::getParameters()`, or use named arguments (`...$args` with string keys on PHP 8.1+), and reject unknown parameters.

### 8. Empty-value handling changed
**Location:** `$args[$key] = $value === '' ? null : $value;`

- The old code turned every `empty()` value except `"0"` into `null`. That included `[]`.
- Array values are now passed through as-is, which is a minor behavior difference.

---

## Pre-existing security issues in code this change touches (still present)

### 9. CSRF: GET `process` triggers state-changing `*_action_process` handlers — High
**Location:** the "Handle process flag" block

- `?...&process` sets `$_POST['process'] = "true"`. Any state-changing `_action_process` method can therefore be triggered with a GET request, such as an `<img>` tag.
- **Fix:**
  - Require a real POST for processing.
  - Verify a CSRF token (`CsrfUtils::verifyCsrfToken`) centrally in `dispatch()` before calling any `_process` method.
  - Stop writing into `$_POST`.

### 10. Incomplete ACL coverage — High
**Location:** `CONTROLLER_ACL_MAP`

- Only `practice_settings` and `prescription` are gated. The following are directly reachable by any authenticated user unless each controller checks ACL internally:
  - `pharmacy`
  - `insurance_company`
  - `insurance_numbers`
  - `x12_partner`
  - `hl7`
  - `document_category`
- Several of these are normally reached as sub-controllers of `practice_settings` (`admin/practice`). Calling them directly bypasses that check.
- `document` and `patient_finder` also depend entirely on internal checks.
- **Fix:** Give every whitelisted controller an ACL entry, and default to deny when an entry is missing.

### 11. ACL is checked only for the top-level controller, not sub-controller delegation — Medium
- Sub-controllers reached through `practice_settings` (passing `sub_action`) inherit only the outer check.
- That is acceptable for admin-gated delegation, but it should be documented or enforced in the sub-controllers themselves.

---

## Minor / maintainability

- **`act()` signature change** (`array $qarray): string`). Any subclass that overrides `act()`, or any caller passing a non-array, will now fatal. Check `C_*` classes and callers.
- **Empty `$qarray` in `act()`.** `$keys[0]` raises an undefined-index warning before `dispatch()` throws. Guard this explicitly.
- **Mixed output style.** `$callMethod` silently discards non-string return values, while some controllers still `echo`. Consider documenting the expected return contract on `ControllerInterface`.