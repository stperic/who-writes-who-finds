## Security review of `Controller.class.php` (`act()` → `dispatch()` refactor)

The refactor improves one thing. Replacing the regex-sanitised, filename-derived controller name with a fixed whitelist (`VALID_CONTROLLERS`) removes the risk of arbitrary `include_once` of `controllers/C_*.class.php` files. It also closes ACL-bypass tricks based on name variants. The findings below remain or are newly introduced.

---

### 1. Action name is no longer sanitised, and the `method_exists()` guard was dropped
- **Location:** `dispatch()`, the `$action` / `$actionMethod` construction and the `is_callable` checks
- **OWASP:** A04 Insecure Design / A05 Security Misconfiguration (arguably A01)
- **Problem:**
  - The old code stripped the action with `preg_replace('/[^A-Za-z0-9_]/', '')`. The new code uses the raw string from the request.
  - The old code also did `is_callable() && method_exists()`. Its own comment said this was needed because Smarty 4's `__call` makes `is_callable()` always true.
  - The new code uses only `is_callable()`, so the "action does not exist" branch is effectively dead.
  - In process mode (`$isProcessing || ...`) the action is invoked unconditionally.
  - An attacker-chosen string therefore reaches `$controllerObj->$method()` and falls through into Smarty's `__call` magic. The Smarty `get*`/`set*` handling is not exercised through the `_action` suffix, but the control is gone, and anything else reachable via `__call` is reachable.
  - Any public method ending in `_action` or `_action_process` on any whitelisted controller can be called, with no per-action authorization.
- **Fix:** Restore `method_exists()`, validate `$action` against `^[A-Za-z0-9_]+$`, and don't run the action when the method doesn't exist.
- **Severity:** Medium

### 2. Arguments are bound by position, not by name
- **Location:** `dispatch()`, `$controllerObj->$method(...array_values($args))`; `act()`
- **OWASP:** A04 Insecure Design
- **Problem:**
  - The docblock claims "order-independent routing", but `array_values($args)` discards the keys. Parameters are passed positionally in the order they appear in the query string.
  - The caller controls order and can add extra parameters. This lets an attacker swap or shift arguments (for example `patient_id`/`doc_id`) or cause parameter-confusion bugs in the action methods.
  - Array-valued inputs (`?id[]=x`) and type mismatches produce `TypeError`s and possibly stack traces.
  - Values are never type-checked or validated.
- **Fix:** Bind by name using reflection (`ReflectionMethod::getParameters()`) or named arguments, ignore unknown keys, and coerce or validate types.
- **Severity:** Medium

### 3. ACL coverage is incomplete, and no per-action authorization exists
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`
- **OWASP:** A01 Broken Access Control (pre-existing, but this change touches and entrenches it)
- **Problem:**
  - Only `practice_settings` and `prescription` are checked.
  - `document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner` and others get no ACL check in the dispatcher.
  - `pharmacy`, `insurance_company`, `x12_partner` and `document_category` are sub-controllers of `practice_settings`. They can now be requested directly with `controller=pharmacy` and skip the `admin/practice` check, unless each controller enforces its own.
  - There is also no authentication or session check inside the dispatcher.
- **Fix:** Add a default-deny ACL for every whitelisted controller, and map every controller to an ACL entry.
- **Severity:** High (if the individual controllers don't enforce their own checks)

### 4. State-changing "process" mode can be triggered via GET, with no CSRF protection
- **Location:** `dispatch()`, `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`
- **OWASP:** A01 / A04 (CSRF)
- **Problem:**
  - A `process` query parameter is promoted into `$_POST`, so a simple link or image tag can trigger `*_action_process` handlers.
  - The dispatcher validates no CSRF token.
  - Because `$isProcessing` is true, the action method is also called unconditionally.
- **Fix:** Require a real POST and verify a CSRF token (`CsrfUtils::verifyCsrfToken`) in the dispatcher.
- **Severity:** Medium–High

### 5. Behaviour change in the failure check: `== false` became `=== false`
- **Location:** `dispatch()`, `if ($controllerObj->_state === false)`
- **OWASP:** A04 Insecure Design
- **Problem:**
  - `_state` defaults to `null`. Previously a process handler that left `_state` as null, 0 or "" short-circuited and skipped the main action.
  - Now the main action runs anyway after a failed or incomplete process step. This could cause unintended rendering or side effects.
- **Fix:** Preserve the original semantics, or audit all controllers for how they set `_state`.
- **Severity:** Low–Medium

### 6. User input in exception messages
- **Location:** `NotFoundHttpException("Action '$action' does not exist on controller: ...")`
- **OWASP:** A03 Injection (reflected XSS) / A05 (information disclosure)
- **Problem:**
  - The raw action string is embedded in the message. If an error handler renders it unescaped, this is reflected XSS.
  - Messages and stack traces may leak internals when debug mode is on.
  - Uncaught `TypeError`s from item 2 have the same exposure.
- **Fix:** Use a generic message, log details server-side, and escape on output.
- **Severity:** Low

### 7. No security logging for denied or invalid dispatches
- **Location:** `dispatch()` and `checkControllerAcl()`
- **OWASP:** A09 Logging and Monitoring Failures
- **Problem:** Invalid controller or action requests and ACL failures are not logged with user, IP and parameters. Probing and enumeration go unnoticed.
- **Severity:** Low

---

**Summary:** The whitelist is a real improvement. Before merging, restore the action-name validation and `method_exists()`, bind arguments by name, and add default-deny ACLs for all controllers. Also require POST and a CSRF token for process actions, and review the `_state` comparison change.