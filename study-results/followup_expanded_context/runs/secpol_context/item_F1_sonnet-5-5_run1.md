# Security review: `Controller::act()` / `dispatch()` refactor

The whitelist of controller names is a real improvement. It replaces a filesystem-path-building `include_once` and removes the old arbitrary-controller-name loading. The ACL logic is also centralized, and the two original checks still apply. However, the refactor drops some defenses and leaves some older weaknesses in place.

## Findings

### 1. Action name is no longer sanitized, and `method_exists()` was dropped
- **Location:** `dispatch()`, the `$action` / `$actionMethod` / `$processMethod` construction, the `is_callable()` checks, and `$controllerObj->$method(...)` in `$callMethod`.
- **OWASP:** A03 Injection / A04 Insecure Design
- **Problem:**
  - The old code stripped the action with `preg_replace('/[^A-Za-z0-9_]/', '', ...)`. The new code uses the raw `$_GET['action']` string (or the second query key via `act()`) to build a method name.
  - The old code also paired `is_callable()` with `method_exists()`, and its comment explained why: Smarty 4's `__call` makes `is_callable()` always true. The new code uses only `is_callable()`. The "action does not exist" 404 branch is effectively dead, and any attacker-chosen string ending in `_action` is dispatched through Smarty's magic `__call`.
  - Attacker-controlled strings now reach Smarty's extension lookup (`class_exists('Smarty_Internal_Method_...')`, autoload). `is_callable([$obj, 'parent::x'])` also accepts special `parent::`/`Class::` forms.
  - In process mode (`$isProcessing ||`), the action is called unconditionally.
  - I did not find a direct RCE, but this is a regression from a strict allow-pattern to unvalidated input in a dynamic method call.
- **Severity:** Medium
- **Fix:** Validate `$action` against `/^[A-Za-z0-9_]+$/`. Restore `method_exists()` together with `is_callable()`. Better, check `method_exists()` and `ReflectionMethod::isPublic()`.

### 2. User-controlled action reflected in exception message
- **Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className")`
- **OWASP:** A03 Injection (XSS)
- **Problem:** `$action` is now raw user input. Previously the echoed value was sanitized to `[A-Za-z0-9_]`. If the application's exception handler renders the message into HTML without escaping, this becomes reflected XSS. It also leaks internals.
- **Severity:** Low to Medium, depending on the error renderer.
- **Fix:** Use a generic message, or escape it, and sanitize the action (see #1).

### 3. ACL enforcement covers only two controllers (pre-existing, but this code is the choke point)
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - Only `practice_settings` and `prescription` have ACL checks. The other whitelisted controllers (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) have none here.
  - `C_PracticeSettings` enforces `admin/practice` in its own constructor, but it calls `dispatch()` on the same sub-controllers. Those sub-controllers are also reachable directly via `controller.php?controller=hl7`, `?document`, `?x12_partner`, and so on, without the `admin/practice` gate.
  - Unless each `C_*` class checks its own ACL (not shown), a low-privileged logged-in user can reach administrative functions such as X12 partner, insurance company, pharmacy, and HL7 management, as well as patient and document data.
- **Severity:** Medium to High, pending verification of the per-controller checks.
- **Fix:** Make the map complete, so that each controller has an entry and a missing entry denies access by default. Do not rely on individual controllers remembering their own checks.

### 4. State-changing "process" triggered via GET (pre-existing, carried forward)
- **Location:** `dispatch()`, the `isset($params['process'])` block that sets `$_POST['process'] = "true"`
- **OWASP:** A01 / A04 (CSRF), A08
- **Problem:**
  - A `process` query parameter is promoted to a POST flag. This means a state-changing `*_action_process` handler can be triggered by a plain GET link or image tag.
  - The dispatcher also has no CSRF token verification. Any CSRF protection is left to each controller.
- **Severity:** Medium
- **Fix:** Require a real POST for `process` and validate a CSRF token in the dispatcher.

### 5. Positional argument confusion despite "order-independent" routing
- **Location:** `dispatch()`, the `$args` build and `...array_values($args)` call, and `act()`
- **OWASP:** A04 Insecure Design
- **Problem:**
  - Remaining query parameters are spread positionally into the action method. Extra or reordered query parameters (for example an injected `&foo=bar`, or `sub_action`) shift values into the wrong parameters.
  - Values may also be arrays (`?id[]=1`) and are passed unchecked.
  - This could cause an action to operate on the wrong ID, for example a delete or edit.
- **Severity:** Low to Medium
- **Fix:** Bind arguments by reflected parameter name, with type validation, rather than by position.

### 6. Behavior change from `== false` to `=== false` on `_state`
- **Location:** `if ($controllerObj->_state === false)`
- **OWASP:** A04 Insecure Design
- **Problem:** `_state` defaults to `null`. The old loose comparison returned early after a process action that did not set `_state`. Now execution falls through to the normal action as well. Handlers that relied on the early return could execute display or action logic twice or unintentionally.
- **Severity:** Low
- **Fix:** Confirm each controller's behavior, or preserve the previous semantics.

### 7. Minor: no logging of rejected dispatch attempts
- **Location:** The `BadRequestHttpException` and `NotFoundHttpException` throws
- **OWASP:** A09 Logging and Monitoring Failures
- **Problem:** Invalid controller or action probes are not logged. The ACL denial may be logged by `AccessDeniedHelper`.
- **Severity:** Low

## Summary
Items 1 and 2 are regressions introduced by this PR and should be fixed before merge. Items 3 and 4 are pre-existing weaknesses in code the PR touches. They are worth addressing here because the PR centralizes the ACL map and dispatch flow.