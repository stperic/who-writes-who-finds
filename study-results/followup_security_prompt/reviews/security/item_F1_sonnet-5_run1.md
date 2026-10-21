## Security Review: `Controller.class.php` Dispatch Refactor

### 1. Unsanitized, attacker-controlled input used to build dynamically-invoked method names
**Location:** `dispatch()` — 
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
$processMethod = "{$actionMethod}_process";
...
$controllerObj->$method(...array_values($args));
```
**OWASP Category:** A01:2021 – Broken Access Control / A03:2021 – Injection (insecure design around dynamic dispatch)

**Problem:** The previous implementation sanitized the action token with `preg_replace("/[^A-Za-z0-9_]/", "", ...)` before using it to build a method name. That whitelist filtering has been dropped entirely in `dispatch()`. `$action` now flows straight from user-supplied request parameters into a dynamically invoked method name (`$controllerObj->$method(...)`), with arbitrary attacker-controlled arguments. Since `Controller` extends `Smarty`, and the code's own (now-deleted) comment explicitly warns that `is_callable()` is unreliable against Smarty 4's internal `__call()` magic method, removing both the character whitelist *and* the `method_exists()` safety check (see #2) significantly increases the chance that attacker-supplied method names reach Smarty's magic dispatch internals with attacker-controlled arguments.

**Severity:** High

---

### 2. `method_exists()` safety check removed; action method invoked unconditionally during processing
**Location:** `dispatch()`:
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException(...);
}
```
**OWASP Category:** A05:2021 – Security Misconfiguration / A01:2021 – Broken Access Control

**Problem:** The original code paired `is_callable()` with an explicit `method_exists()` check specifically because Smarty's `__call()` causes `is_callable()` to return `true` even for undefined methods. That second check has been removed in this refactor, and the condition `$isProcessing || is_callable(...)` means that whenever `$_POST['process'] === 'true'`, the action method is invoked **unconditionally**, bypassing the callability check altogether. Combined with finding #1 (unsanitized `$action`), this materially weakens the "fail closed" guarantee that only legitimate, developer-defined `_action` methods can be called.

**Severity:** High

---

### 3. Attacker-controlled values reflected into exception messages
**Location:** `dispatch()`:
```php
throw new BadRequestHttpException("Missing or invalid 'controller' parameter");
...
throw new NotFoundHttpException("Unable to load controller: $className");
...
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```
**OWASP Category:** A03:2021 – Injection (Reflected XSS) / A09:2021 – Security Logging and Monitoring Failures (poor error handling hygiene)

**Problem:** `$action` is attacker-controlled and unsanitized (per #1) and is embedded directly into exception messages. If the application's global exception handler renders these messages to the browser without HTML-encoding (common in debug/dev environments, and sometimes in custom error templates), this is a reflected XSS vector. Even without XSS, verbose error messages revealing internal class/controller names aid reconnaissance.

**Severity:** Low–Medium (impact depends on how the Symfony exception listener renders messages in this app)

---

### 4. Centralized ACL whitelist covers only 2 of 10 routable controllers
**Location:** `CONTROLLER_ACL_MAP` vs. `VALID_CONTROLLERS`

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** The new `VALID_CONTROLLERS` whitelist formally exposes 10 dispatchable controllers (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `practice_settings`, `prescription`, `x12_partner`), but `CONTROLLER_ACL_MAP` only enforces ACL for `practice_settings` and `prescription` — identical to the old code. This PR is a good opportunity to centralize authorization per-controller, but it preserves the gap: controllers handling clearly sensitive data (patient documents, HL7 messages, insurance records) have no enforcement at this dispatch layer and rely entirely on internal checks inside each controller class (not visible in this diff). This should be explicitly verified; if any of these controllers lack their own internal ACL checks, this is an access-control gap.

**Severity:** Medium (verification required; may be pre-existing, but the refactor is the natural place to close it)

---

### Positive observations (not vulnerabilities)
- Resolving the controller class name via a hardcoded whitelist (`VALID_CONTROLLERS`) rather than deriving it purely from regex-sanitized user input is a solid improvement — it meaningfully reduces risk of arbitrary file inclusion/path traversal via the controller parameter.
- Strict `isset()` whitelist check on `$controllerParam` before use is good practice.

### Summary
The most important issues are **#1 and #2**: the refactor silently drops two layers of defense (character sanitization of the action name, and the `method_exists()` double-check against Smarty's `__call` magic method) that were deliberately present in the legacy code specifically to prevent unintended dynamic method invocation. These should be restored before merge. Findings #3 and #4 are secondary hardening items worth addressing or at least confirming are mitigated elsewhere.