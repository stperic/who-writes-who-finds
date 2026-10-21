# Code Review: `Controller::act()` / `dispatch()` refactor

The controller whitelist is a real improvement. However, this PR also removes action-name sanitization and the `method_exists()` guard. It also leaves several authorization and CSRF gaps in the routing path untouched.

---

## High

### 1. Action name is no longer sanitized (XSS and method-name injection)
**Location:** `dispatch()`, `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`

**Problem:**
- The old code ran `preg_replace("/[^A-Za-z0-9_]/", "", ...)` on the action. The new code uses the raw request string in three places:
  - the method name `"{$action}_action"`,
  - `$controllerObj->_current_action`,
  - the exception message.
- `_current_action` is consumed by `_link()` and by templates to build URLs and markup. An attacker-controlled value there (e.g. `action="><script>…`) creates a reflected XSS risk wherever it is echoed.
- The exception message also reflects it. That is a problem if the error handler renders messages to the browser.

**Fix:** Validate the action strictly, e.g. `preg_match('/^[A-Za-z0-9_]+$/', $action)`. Reject anything else with `BadRequestHttpException`.

### 2. `method_exists()` guard was removed, so `is_callable()` is always true
**Location:** `dispatch()`, the `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])` checks.

**Problem:**
- The deleted comment explained this exact issue. Smarty 4 defines `__call`, so `is_callable()` returns true for any method name on a `Smarty` subclass.
- As a result:
  - The "action does not exist" branch is unreachable.
  - Any action name, including non-existent `_action_process` methods, is routed into Smarty's `__call` / extension handler.
- The likely outcomes are an uncaught Smarty exception or error instead of a 404. In the worst case, a Smarty extension method whose name happens to end in `_action` / `_action_process` gets invoked.
- Combined with issue #1, this gives attackers broad control over which magic dispatch paths run.

**Fix:** Restore `method_exists($controllerObj, $method)`. Ideally, also require the method to be public and declared on the controller class, e.g. via `ReflectionMethod`.

### 3. Sub-controllers are directly reachable without their parent's ACL (pre-existing; preserved by the whitelist)
**Location:** `VALID_CONTROLLERS` and `CONTROLLER_ACL_MAP`.

**Problem:**
- `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, `document_category`, and `hl7` are normally reached via `practice_settings`, which is gated by `admin/practice`.
- All of them are whitelisted as top-level controllers with no ACL entry. So `controller.php?pharmacy&edit&process=true` (or `controller=pharmacy` via `dispatch()`) skips the `admin/practice` check entirely.
- `document` and `patient_finder` likewise have no dispatcher-level ACL.
- This PR formalizes the list, which makes it the natural place to close the gap.

**Fix:** Add ACL entries for every whitelisted controller, or default-deny any controller missing from `CONTROLLER_ACL_MAP`.

### 4. State-changing "process" actions can be triggered via GET (pre-existing; CSRF)
**Location:** `dispatch()`, `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`

**Problem:**
- A GET parameter promotes itself to `$_POST['process']`, which runs the `*_action_process` handlers that save data.
- No CSRF token is verified in the dispatcher. A link or `<img>` tag can therefore trigger writes (e.g. saving pharmacy, insurance, or prescription records) for a logged-in user.

**Fix:**
- Only run process handlers on actual POST requests.
- Verify the CSRF token (`CsrfUtils::verifyCsrfToken`) centrally in `dispatch()` before calling any process method.

---

## Medium

### 5. Uncaught HTTP exceptions replace `echo` + `exit`
**Location:** `throw new BadRequestHttpException`, `throw new NotFoundHttpException`.

**Problem:**
- Unless `controller.php` (and every other `act()` caller, including nested sub-controller delegation) wraps this in a handler, these become fatal errors or 500 responses.
- With `display_errors` enabled, they may expose stack traces and file paths.
- The diff does not show any caller-side handling.

**Fix:** Confirm that every call site catches `HttpExceptionInterface` and renders an appropriate response.

### 6. Integer keys break positional-key skipping in `act()`
**Location:** `act()`, `if ($key === $controller || $key === $positionalAction)`.

**Problem:**
- PHP turns numeric query keys into `int`, but `$controller` and `$positionalAction` are cast to `string`. With strict comparison they never match.
- Example: `?document&5` would use `"5"` as the action and *also* pass `5` as an argument.
- Separately, a parameter whose name equals the default `'default'` would be dropped silently.

**Fix:** Skip by position (index 0 and 1 of `$keys`) rather than by value.

### 7. Argument-passing semantics changed
**Location:** `dispatch()`, construction of `$args` and the `array_values($args)` call.

**Problem:**
- **Arguments now include values the old code excluded:**
  - The old code passed only keys *after* the first two, in order. The new code passes all non-reserved params.
  - When called via `dispatch()`, this includes arbitrary extra query params, such as tracking params or `csrf_token_form`.
  - These shift into positional method arguments and can land in the wrong parameter slots.
- **`sub_action` can be overwritten:** a literal `sub_action=` in the URL clobbers the renamed `action`.
- **Empty-to-`null` conversion is narrower:** the old code mapped all `empty()` values except `"0"` to `null`. The new code maps only `''`, so `null` and array values now behave differently.

**Fix:**
- Document which params are positional.
- Consider passing only the expected arguments, or switch to named arguments.

### 8. Non-string action results are silently discarded
**Location:** `$callMethod`, `return is_string($result) ? $result : '';`.

**Problem:** Previously any return value (int, `Stringable`, etc.) was concatenated into the output. Now it is dropped. Verify that no action relies on this.

### 9. Signature tightening may break subclasses
**Location:** `act(array $qarray): string`, `implements ControllerInterface`.

**Problem:** Any `C_*` subclass that overrides `act()` or `dispatch()` without compatible types will cause a fatal error at class load.

**Fix:** Grep `controllers/` for overrides before merging.

---

## Low

### 10. `dispatch()` mutates superglobals
**Location:** `dispatch()`, `unset($_GET['process'])`, `$_POST['process'] = "true"`, and `$isProcessing = ($_POST['process'] ?? '') === 'true'`.

**Problem:**
- The method accepts `$params` but still rewrites `$_GET` / `$_POST`.
- It also decides `$isProcessing` from `$_POST` rather than from `$params`.
- This makes behavior depend on global state and makes testing or nested dispatch error-prone.

### 11. Empty `$qarray` in `act()`
**Location:** `act()`, `$keys[0]`.

**Problem:** An empty array triggers an undefined-index warning before the `BadRequest` is thrown.

**Fix:** Guard with `if ($qarray === [])`.

### 12. Edge case: `process` as the second positional key
**Location:** `act()`, positional action extraction.

**Problem:** `process` is now evaluated after the positional keys are extracted. A URL like `?document&process` would yield the action `process`, whereas the old code unset `process` first.