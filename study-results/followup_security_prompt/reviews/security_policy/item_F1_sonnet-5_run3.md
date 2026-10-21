# Security Review: `Controller.class.php` Routing Refactor

## Summary
This diff refactors `act()`/introduces `dispatch()` for controller routing. While it improves some aspects (controller name whitelisting, stricter `===` comparison for the `process` flag), it also **silently drops a security-relevant check that was present in the old code for a documented reason**, and it removes input sanitization that existed as defense-in-depth. Several pre-existing design issues are also carried forward unchanged.

---

### 1. Removal of `method_exists()` check defeats whitelisting of action methods
**Location:** `dispatch()` — the `is_callable([$controllerObj, $processMethod])` / `is_callable([$controllerObj, $actionMethod])` checks.

**OWASP Category:** A01 – Broken Access Control / A04 – Insecure Design

**Problem:** The old code had an explicit comment:
> "can no longer rely on is_callable since smarty 4 invokes a `__call` function deep within its classes, thus `is_callable()` is always true. so need to do both the `is_callable` and a `method_exists()` check."

The old code therefore gated every call with `is_callable(...) && method_exists(...)`. The new `dispatch()` drops `method_exists()` entirely and relies only on `is_callable()`. Since `Controller extends Smarty`, and Smarty implements `__call()`, `is_callable()` will return `true` for essentially **any** action name, regardless of whether a real `{action}_action` method exists. This means:
- The intended "action does not exist" validation (`NotFoundHttpException`) is effectively unreachable for most inputs.
- Arbitrary attacker-supplied action strings will be passed through to `$controllerObj->$method(...)`, which will fall through to Smarty's magic `__call()` with attacker-controlled method name and arguments, with behavior that is unvalidated and was explicitly called out as unsafe in the original code.

This reopens a bug that was previously fixed on purpose, with no comment explaining why the safeguard was removed.

**Severity:** High

---

### 2. Unsanitized `action` parameter reflected into exception message
**Location:** `dispatch()`:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
...
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```

**OWASP Category:** A03 – Injection (Reflected XSS)

**Problem:** The old code sanitized the action value with `preg_replace("/[^A-Za-z0-9_]/", "", ...)` before it was used anywhere, including in the old `echo "...$c_action..."` debug message. The new code uses the raw, attacker-controlled `$action` value directly in an exception message. If this exception message is ever rendered to the browser (e.g., in a dev/debug error page, or a custom handler that echoes `getMessage()` without escaping), this is a straightforward reflected XSS vector. Even if currently caught safely, this is a regression in defense-in-depth compared to the previous sanitization.

**Severity:** Medium (severity depends on how exceptions are rendered downstream — verify the global exception handler escapes output)

---

### 3. State-changing "process" flag triggerable via GET (CSRF-prone), pre-existing
**Location:** `dispatch()`:
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```

**OWASP Category:** A01 – Broken Access Control (CSRF-adjacent)

**Problem:** A simple GET request with `?process=1` forces subsequent code to treat the request as a form submission (`$_POST['process'] = "true"`), triggering `_action_process` handlers that presumably perform state-changing operations (e.g., writing prescriptions, updating practice settings, updating insurance records). There's no CSRF token verification visible in this layer. This logic is carried over unchanged from the original code, but it's worth flagging since this change touches the exact code path and widens it to all 10 controllers via the new whitelist, including sensitive ones like `prescription` and `practice_settings`.

**Severity:** Medium (pre-existing, but worth remediating now since this routing path is being actively worked on)

---

### 4. Positional argument order dependent on attacker-controlled parameter order
**Location:** `act()` building `$params` from `$qarray`, and `dispatch()`:
```php
$args[$key] = $value === '' ? null : $value;
...
$controllerObj->$method(...array_values($args));
```

**OWASP Category:** A04 – Insecure Design

**Problem:** Arguments are still passed to controller action methods **positionally**, based on the iteration order of an associative array built from attacker-supplied query parameters. Because PHP preserves insertion order and the order of keys in `$_GET`/`$_POST` is attacker-controlled, a caller can reorder parameters in the URL to change which value lands in which positional slot. Depending on how downstream `_action`/`_action_process` methods use these positional arguments (e.g., `$patientId, $isAdminFlag`), this can lead to logic/authorization confusion (e.g., IDOR-style parameter swapping). This behavior exists in the old code too (via `array_reverse(array_keys($qarray))`), but the refactor changes exactly how the order is derived (`act()` now preserves original key order instead of reversing), which may silently change argument ordering for existing controllers that depended on the old semantics — this should be carefully regression-tested against every listed controller (`document`, `hl7`, `pharmacy`, `prescription`, etc.).

**Severity:** Medium–High (depends on controller implementations; recommend converting to named-argument dispatch rather than positional)

---

### 5. ACL enforcement only covers 2 of 10 whitelisted controllers
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`

**OWASP Category:** A01 – Broken Access Control

**Problem:** Only `practice_settings` and `prescription` have centralized ACL checks in this routing layer. The other 8 controllers (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) — several of which touch PHI (documents, insurance, pharmacy data) — have **no ACL check at this layer** at all. This mirrors the pre-existing behavior, so it's not a new regression, but since this diff formalizes and "productionizes" the routing (adding an explicit whitelist and interface), it's a good time to verify that each of these controllers performs its own sufficient ACL enforcement internally. If any controller relies on `Controller::act()` for ACL (as `practice_settings`/`prescription` apparently do), the other 8 may be unintentionally unprotected.

**Severity:** Medium (needs verification against each controller's internal checks)

---

### 6. Exception-based error handling may leak internal details
**Location:** `dispatch()` throwing `BadRequestHttpException` / `NotFoundHttpException` instead of `echo ... exit;`

**OWASP Category:** A05 – Security Misconfiguration / A09 – Logging & Monitoring Failures

**Problem:** The switch from controlled `echo`+`exit` to thrown exceptions is good practice *if* there's a global exception handler producing generic error pages. If uncaught, PHP/Symfony's default behavior (especially in dev or misconfigured prod environments) can emit stack traces including file paths and internal class names. Also, there is no logging of these failure events (invalid controller, missing action, ACL denial) for security monitoring purposes — neither old nor new code logs these, which is a gap for detecting probing/attack attempts against this routing endpoint.

**Severity:** Low–Medium (configuration-dependent)

---

### 7. No input validation on `controller` beyond array key lookup (minor, but verify)
**Location:** `dispatch()`:
```php
$controllerParam = is_string($params['controller'] ?? null) ? $params['controller'] : '';
if (!isset(self::VALID_CONTROLLERS[$controllerParam])) { ... }
```
**OWASP Category:** N/A — noted as a positive control
**Problem:** This is actually a **security improvement** over the old code (which built class/file names from a regex-sanitized but otherwise unrestricted string, allowing inclusion of any `C_*.class.php` file that happened to exist on disk). The new whitelist approach meaningfully reduces attack surface for arbitrary file inclusion. No action needed — mentioned for completeness since the review is asked to also note code this change touches.

**Severity:** Informational (improvement, not a vulnerability)

---

## Recommendations
1. Restore the `method_exists()` check alongside `is_callable()` (or better, use `ReflectionClass::hasMethod()`), since `is_callable()` is not reliable on `Smarty`-derived classes.
2. Sanitize/whitelist the `action` parameter (e.g., `^[A-Za-z0-9_]+$`) before use anywhere, including in exception messages.
3. Add CSRF token validation for any `_action_process` handler that performs a state change, independent of the `process` GET/POST flag.
4. Migrate from positional to explicitly named argument passing to action methods, eliminating reliance on parameter order.
5. Audit each of the 10 whitelisted controllers to confirm they perform their own ACL checks, or extend `CONTROLLER_ACL_MAP` to cover all of them.
6. Ensure a global exception handler safely renders `BadRequestHttpException`/`NotFoundHttpException` without leaking stack traces, and add logging for these events (invalid controller/action, ACL denial) for monitoring.