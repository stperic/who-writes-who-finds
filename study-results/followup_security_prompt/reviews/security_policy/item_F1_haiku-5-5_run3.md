# Security Review: `Controller.class.php` dispatch refactor

## Summary

No critical or high-severity issues were found in the new code. The class-name whitelist (`VALID_CONTROLLERS`) prevents arbitrary file inclusion and class instantiation, and the ACL check runs before dispatch. The refactor does introduce several medium-severity problems, and the old code's weaknesses carry over in places. I recommend fixing findings 1 and 2 before merge.

## Findings

### 1. Unsanitized user input reflected in exception messages
- **Location:** `dispatch()`, `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
- **OWASP:** A03:2021 Injection (reflected XSS), A05 Security Misconfiguration (information exposure)
- **Problem:** `$action` comes straight from `$params['action']` with no sanitization. The old code ran action names through `preg_replace("/[^A-Za-z0-9_]/", "", ...)` before echoing them. The new code drops that filter, so any value containing HTML or script can reach the exception message. If the front controller or Symfony's error renderer outputs the message as HTML (for example, in debug mode), this is reflected XSS. The message also discloses class names. Debug-mode stack traces would make the disclosure worse.
- **Severity:** Medium (High if the error page renders HTML unescaped; Low if it is always plain text)
- **Fix:** Validate `action` against `/^[A-Za-z0-9_]+$/` before use, and escape or omit user input in exception messages.

### 2. Process-mode branch calls an unvalidated method name
- **Location:** `dispatch()`, the block `if ($isProcessing || is_callable(...)) { $output .= $callMethod($actionMethod); }`
- **OWASP:** A04:2021 Insecure Design, A03:2021 Injection (dynamic method invocation)
- **Problem:** When `$isProcessing` is true, the code calls `$actionMethod` without checking `is_callable()`. The `_action_process` method is checked, but the `_action` method is not. Any name matching `{anything}_action` is therefore invoked on the controller object. For a Smarty-derived class, a missing method may reach `Smarty::__call()`, and the code comment says Smarty 4 relies on `__call` internally. The reachable surface depends on what `__call` does with arbitrary names, which I could not verify from the diff. The original code had the same unchecked call in process mode, so this is inherited, but the refactor touches it and the `||` logic makes the gap explicit.
- **Severity:** Medium
- **Fix:** Require `is_callable([$controllerObj, $actionMethod])` in every branch. Return a 404 when the method does not exist, whether or not the request is in process mode.

### 3. Process mode is reachable via GET, enabling CSRF-style state changes
- **Location:** `dispatch()`, `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`
- **OWASP:** A01:2021 Broken Access Control (CSRF), A04:2021 Insecure Design
- **Problem:** A `process` parameter in the query string, such as `controller.php?controller=...&action=...&process=true`, is promoted to `$_POST['process']`. This lets a state-changing `*_action_process` method run from a GET link that a logged-in user can be tricked into opening. The pattern predates this diff, but the diff keeps it and extends it to `dispatch()`, which is the new public entry point.
- **Severity:** Medium (depends on whether each `*_process` method enforces its own CSRF token)
- **Fix:** Accept `process` only from POST, and verify a CSRF token in every `*_process` method.

### 4. Arguments are bound by query-string order, not by name
- **Location:** `dispatch()`, the `$args` build loop and `$callMethod(...array_values($args))`
- **OWASP:** A04:2021 Insecure Design, A08:2021 Software and Data Integrity Failures
- **Problem:** The docblock says routing is "order-independent," but parameters are passed positionally in the order they appear in `$params`. An action signature such as `action($patient_id, $doc_id)` receives values in URL order. A request that reorders the parameters can swap security-relevant IDs and make the action operate on a different record than the one the caller's ACL check covered. The actual impact depends on each action's internal checks.
- **Severity:** Low to Medium
- **Fix:** Bind arguments by name with reflection (`ReflectionMethod::getParameters()`), or pass a single validated request object. At minimum, correct the docblock.

### 5. Raw array and object values are passed to action methods
- **Location:** `dispatch()`, `$args[$key] = $value === '' ? null : $value;`
- **OWASP:** A03:2021 Injection (type confusion), A04:2021 Insecure Design
- **Problem:** `$_GET` values may be arrays (`foo[]=1`). These are passed unchanged into action methods. Depending on how a method uses the value, this can cause type errors that disclose internals, or it can reach string-only sinks such as SQL builders without a type guard. The old code had the same behavior.
- **Severity:** Low
- **Fix:** Require scalar values (`is_scalar()`) for action arguments, and reject or sanitize arrays.

### 6. ACL coverage is limited to two controllers
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** Only `practice_settings` and `prescription` have a central ACL check. The whitelist also exposes `hl7`, `x12_partner`, `insurance_numbers`, `insurance_company`, `pharmacy`, `document`, `document_category`, and `patient_finder`. Some of these, such as HL7 and X12 partner configuration, are administrative. Their access control now depends entirely on each controller's own code, which is not part of this diff. The old code had the same gap, but the whitelist now makes these endpoints explicitly reachable.
- **Severity:** Medium (defense in depth; not verifiable from the diff alone)
- **Fix:** Add ACL entries for each administrative controller, or enforce a default-deny ACL check in `dispatch()`. Confirm that each controller performs its own check.

### 7. No audit logging of dispatch decisions
- **Location:** `dispatch()` (ACL denials, invalid controller and action names)
- **OWASP:** A09:2021 Security Logging and Monitoring Failures
- **Problem:** Invalid controller names, missing actions, and process-mode invocations are not logged. Probing and privilege-escalation attempts through the router would leave no trace in the application log, apart from whatever `AccessDeniedHelper` records.
- **Severity:** Low
- **Fix:** Log rejected dispatch attempts with the user ID, controller, action, and client IP.

## Positive observations
- The controller name is resolved through a fixed whitelist before any file or class name is built, which blocks path traversal and arbitrary class instantiation.
- `preg_replace` on the class name and the `i_once` path are replaced by a whitelist lookup, which is stricter than before.
- The ACL check runs before controller loading and action dispatch.
- The diff contains no SQL, no cryptography, and no outbound requests, so those OWASP categories do not apply.

## Verdict
**Changes requested.** Address findings 1 and 2 before merge, and review finding 3 for every `*_process` method. Findings 4 through 7 should be tracked as follow-up work.