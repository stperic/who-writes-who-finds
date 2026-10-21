## Security Review: `Controller.class.php` routing refactor

**Verdict:** I would not merge this as-is. The controller whitelist and the class-name construction are sound, but the argument binding and the callable check introduce real problems. The most important is that the new "order-independent" routing is actually order-dependent.

### Findings

**1. Positional argument binding from attacker-controlled query order**
- **Location:** `dispatch()`, the `$args` loop and `$callMethod(...array_values($args))`
- **OWASP category:** A01 Broken Access Control (parameter confusion/IDOR risk), A04 Insecure Design
- **Problem:** Arguments are built by iterating `$params` in URL order and then spread positionally with `array_values()`. The PHP method signature therefore decides which value binds to which parameter, but the URL order decides what each value is. The doc comment promises order-independent routing, which this does not deliver. An attacker can omit or reorder query parameters to shift values into different parameter slots. If a controller method has optional or defaulted parameters, the attacker can also make a value land in a slot the code assumes is server-controlled (for example, a patient or document ID that is checked for ownership). Extra unexpected parameters are also silently appended as positional arguments.
- **Severity:** High (Medium if no controller relies on the positional slots for authorization)
- **Fix:** Bind arguments by name using reflection (`ReflectionMethod::getParameters()`), reject unknown parameters, and never spread `array_values()` of an unordered map.

**2. Weakened method-existence check (`is_callable` without `method_exists`)**
- **Location:** `dispatch()`, `is_callable([$controllerObj, $processMethod])` and `if ($isProcessing || is_callable([$controllerObj, $actionMethod]))`
- **OWASP category:** A05 Security Misconfiguration / A04 Insecure Design
- **Problem:** The original code required both `is_callable()` and `method_exists()` because the comment in the removed code notes that Smarty 4 `__call` makes `is_callable()` return true for arbitrary names. The new code drops `method_exists()`. Also, when `$isProcessing` is true, the action method is called unconditionally, so a nonexistent action goes straight to `$controllerObj->$method(...)`. That can route an attacker-chosen `{action}_action` name into Smarty's magic `__call`, or produce a fatal error that leaks internal details.
- **Severity:** Medium
- **Fix:** Restore `method_exists()`, check the action method once, and require it to be public and declared on the controller (for example with `ReflectionMethod` and an `isPublic()` check). Apply the same check in both branches.

**3. Unsanitized action name reflected in error message**
- **Location:** `dispatch()`, `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
- **OWASP category:** A03 Injection (reflected XSS, depending on the exception handler)
- **Problem:** The original code sanitized the action with `preg_replace("/[^A-Za-z0-9_]/", ...)`. The new code uses the raw `$action` value. If the global exception handler renders the message as HTML without escaping, an attacker can inject script through the `action` parameter.
- **Severity:** Medium (Low if the handler is known to escape output)
- **Fix:** Validate `$action` against `/^[A-Za-z0-9_]+$/` before use, and HTML-escape any value that is echoed.

**4. Missing default-deny ACL on whitelisted controllers**
- **Location:** `checkControllerAcl()` and `CONTROLLER_ACL_MAP`
- **OWASP category:** A01 Broken Access Control
- **Problem:** Only `practice_settings` and `prescription` have an ACL requirement. The other eight whitelisted controllers (including `document`, `hl7`, `insurance_numbers`, and `x12_partner`) are dispatched with no check at this layer. This matches the old `act()` behavior, so it is not a regression, but the new whitelist is a natural place to enforce ACLs and it does not.
- **Severity:** Low to Medium (depends on whether each controller enforces its own ACL)
- **Fix:** Require an ACL entry for every whitelisted controller (default deny), or document that each controller must enforce its own checks.

**5. State-changing actions triggered by GET parameter**
- **Location:** `dispatch()`, `if (isset($params['process']))`
- **OWASP category:** A01 Broken Access Control (CSRF-adjacent)
- **Problem:** A `process` parameter in the query string sets `$_POST['process']`, so state-changing actions can be triggered by a GET request, making them reachable by cross-site link or image tags. The original code had the same behavior (`isset($_GET['process'])`), so this is pre-existing, but the diff preserves it in the new entry point.
- **Severity:** Low (pre-existing)
- **Fix:** Accept `process` only from POST, and rely on a CSRF token for state changes.

**6. Type confusion from array-valued parameters**
- **Location:** `dispatch()`, the `$args` loop
- **OWASP category:** A04 Insecure Design / A09 Logging and Monitoring (error leakage)
- **Problem:** Query values are passed through without checking their type. An array-valued parameter (for example `x[]=1`) reaching a typed method signature causes a `TypeError`. That can leak stack traces or internal paths if error display is enabled.
- **Severity:** Low
- **Fix:** Reject non-scalar values for controller arguments and catch `TypeError` with a generic 400 response.

**7. No audit logging for dispatch or ACL denial**
- **Location:** `dispatch()` and `checkControllerAcl()`
- **OWASP category:** A09 Security Logging and Monitoring Failures
- **Problem:** Controller dispatch and ACL denials are not logged, so access to sensitive controllers (prescriptions, practice settings, documents) cannot be audited. `AccessDeniedHelper` may log, but that is not verified here.
- **Severity:** Low

### Positive observations
- The controller name is taken only from a whitelist (`VALID_CONTROLLERS`), so the class name and file path cannot be attacker-controlled. This removes the original `preg_replace`-based path construction concern.
- `new $className()` and `i_once($controllerFile)` both use the whitelisted value.
- The `process` flag handling is unchanged in behavior, and the ACL check runs on the final validated controller name, so key collisions in `act()` cannot bypass it.
- The original `preg_replace` sanitization is replaced by an explicit whitelist, which is a clear improvement.

### Summary

| # | Issue | OWASP | Severity |
|---|-------|-------|----------|
| 1 | Positional argument binding from query order | A01 / A04 | High |
| 2 | `is_callable` without `method_exists` | A05 / A04 | Medium |
| 3 | Unsanitized action reflected in exception | A03 | Medium |
| 4 | No default-deny ACL on other controllers | A01 | Low–Medium |
| 5 | `process` state change via GET | A01 | Low (pre-existing) |
| 6 | Array values cause TypeError / error leakage | A04 / A09 | Low |
| 7 | No audit logging of dispatch or denial | A09 | Low |

Findings 1 through 3 should be fixed before merge. Findings 4 through 7 can be tracked as follow-ups.