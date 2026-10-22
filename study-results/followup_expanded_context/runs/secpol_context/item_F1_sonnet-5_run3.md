# Security Review: `Controller.class.php` refactor

## 1. Broken Access Control — Incomplete centralized ACL enforcement
**Location:** `Controller::checkControllerAcl()` / `CONTROLLER_ACL_MAP` / `dispatch()`
**OWASP Category:** A01:2021 – Broken Access Control
**Problem:**
`CONTROLLER_ACL_MAP` only contains `practice_settings` and `prescription`. All other entries in `VALID_CONTROLLERS` (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) get **no ACL check at all** from the dispatcher.

Previously, controllers such as pharmacy, insurance_company, x12_partner, document_category, and hl7 were only reachable in practice *through* `C_PracticeSettings`, whose constructor enforces `admin/practice`. But `dispatch()` is now a `public` method and `controller=pharmacy` (etc.) is in the explicit whitelist, so it can be invoked **directly** (e.g. `controller.php?controller=pharmacy&action=list`), completely bypassing `C_PracticeSettings`'s ACL gate — unless each individual sub-controller (`C_Pharmacy`, `C_InsuranceCompany`, `C_X12Partner`, `C_DocumentCategory`, `C_Hl7`, `C_PatientFinder`, `C_InsuranceNumbers`, `C_Document`) independently re-checks ACLs in its own constructor. These files were not included for review — this needs to be verified. If any of them rely on being invoked only through the parent controller, this is a privilege-escalation / unauthorized-access vulnerability exposed by making the whitelist and `dispatch()` a clean, directly-reachable public API.

**Severity:** High (pending verification of the individual controllers’ own ACL checks)

---

## 2. Injection / Reflected XSS — unsanitized `action` parameter
**Location:** `dispatch()`, `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';` and `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
**OWASP Category:** A03:2021 – Injection (XSS)
**Problem:**
The old code sanitized the action name with `preg_replace("/[^A-Za-z0-9_]/", "", ...)` before using it to build a method name or echoing it. The new code does **not** sanitize `$action` at all before (a) embedding it into a dynamic method name (`"{$action}_action"`), and (b) embedding it verbatim into an exception message. If the unhandled exception is ever rendered into an HTML response without proper output-encoding (common for debug/dev error pages, and not guaranteed for custom exception handlers), this is a reflected XSS sink driven directly by `$_GET['action']`. Even ignoring XSS, removing input validation before using user input to build a method name is an unnecessary regression in defense-in-depth.
**Severity:** Medium–High (depends on how the exception is ultimately rendered)

---

## 3. Insecure Design — reintroduction of a previously-fixed Smarty `__call()` bypass
**Location:** `dispatch()`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... } else { throw new NotFoundHttpException(...); }
```
**OWASP Category:** A04:2021 – Insecure Design / A05 – Security Misconfiguration
**Problem:**
The original code had an explicit comment and check:
> "can no longer rely on is_callable since smarty 4 invokes a `__call` function deep within its classes, thus `is_callable()` is always true. so need to do both the `is_callable` and a `method_exists()` check."

The refactor drops the `method_exists()` half of that check in both branches. Since `is_callable()` is always `true` due to Smarty's magic `__call()`, the `else` branch that is supposed to reject non-existent actions (`NotFoundHttpException`) can effectively never execute — *any* action name will fall through to actually calling `$controllerObj->$actionMethod(...)`, which will silently invoke Smarty’s internal `__call()` magic method with attacker-influenced method/argument data instead of being rejected. This reopens a bug that was deliberately patched, with unknown downstream behavior inside Smarty’s `__call()`.
**Severity:** Medium

---

## 4. Broken Access Control / CSRF-enabling pattern — GET-triggered “process” flag (pre-existing, preserved)
**Location:** `dispatch()`:
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```
**OWASP Category:** A01:2021 – Broken Access Control (CSRF-adjacent)
**Problem:**
A simple GET request containing `process` forges `$_POST['process'] = "true"`, causing the `_action_process` (state-changing) handler to run as if a POST had occurred. There is no CSRF token validation at this layer, so a crafted link/image/iframe pointing at, e.g., `controller.php?controller=prescription&action=...&process=1` can trigger prescription-processing logic via a cross-site GET. This exists in the pre-change code too, but is carried forward unchanged by this diff.
**Severity:** Medium–High (pre-existing)

---

## 5. Information Disclosure via exception messages
**Location:** `dispatch()` — `BadRequestHttpException`, `NotFoundHttpException`, and `checkControllerAcl()` messages include internal class names, ACL section/value names, and attacker-supplied strings.
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures / minor A05
**Problem:** If these exceptions bubble up to an end-user-facing error page (rather than being logged and replaced with a generic message), internal implementation details (controller class names, ACL section/value naming) are disclosed, aiding reconnaissance.
**Severity:** Low

---

## 6. Missing security logging for suspicious routing attempts
**Location:** `dispatch()` — invalid controller/action/ACL-denied paths
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
**Problem:** No audit log entry is created when an invalid controller is requested, an unknown action is requested, or an ACL check fails (`AccessDeniedHelper::denyWithTemplate` — not shown but worth confirming it logs). Repeated invalid `controller=`/`action=` probing (which would now hit a clean whitelist check) is a useful attack indicator that isn't captured.
**Severity:** Low

---

## Positive note
Replacing the old regex-sanitized, dynamically-constructed class name (`"C_" . ucfirst(...)`) with an explicit `VALID_CONTROLLERS` whitelist lookup is a genuine security improvement — it removes a theoretical arbitrary-file-inclusion-by-filename-guessing vector for the controller class itself (though the `action` method-name construction, per finding #2/#3, does not get the same treatment).

---

### Summary of action items
1. Verify (or add) per-controller ACL checks for every entry in `VALID_CONTROLLERS`, not just `practice_settings`/`prescription`, since `dispatch()` is now a direct, public, whitelisted entry point.
2. Sanitize/whitelist the `action` parameter the same way `controller` is now sanitized (e.g., restrict to `[A-Za-z0-9_]`), and avoid reflecting raw user input into exception messages.
3. Restore the `method_exists()` check alongside `is_callable()` to prevent unintended fallthrough into Smarty’s `__call()`.
4. Re-evaluate the GET-triggered `process` flag for CSRF exposure; add CSRF token validation to state-changing `_action_process` handlers.
5. Ensure exceptions thrown here are caught and converted to generic, logged error responses rather than reflecting internal details to the client.