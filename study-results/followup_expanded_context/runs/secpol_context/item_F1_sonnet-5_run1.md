# Security Review – `Controller.class.php` diff

## 1. Loss of `method_exists()` guard defeats the action‑existence check (new regression)

**Location:** `Controller::dispatch()`, the two `is_callable([$controllerObj, …])` checks.

**OWASP Category:** A04:2021 – Insecure Design (also related to A03 – Injection, CWE‑470 Unsafe Reflection)

**Problem:**
The old code explicitly checked **both** `is_callable()` *and* `method_exists()`, with a comment explaining why:

```php
// can no longer rely on is_callable since smarty 4 invokes a __call function deep within
// its classes, thus is_callable() is always true. so need to do both the is_callable
// and a method_exists() check.
```

The new code only checks `is_callable()`:

```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... } else { throw new NotFoundHttpException(...); }
```

Since `$controllerObj` ultimately extends `Smarty`, which implements `__call()`, `is_callable()` on it is **always true**, regardless of whether `"{$action}_action"` really exists. This means:

* The `NotFoundHttpException` branch for unknown actions is now **unreachable**.
* Any attacker-supplied `action` value will result in an attempt to invoke `"{$action}_action"` / `"{$action}_action_process"` on the controller object, falling through to Smarty's `__call()` magic method instead of being rejected.

This silently reintroduces exactly the bug the original comment warned about, and removes a previously-enforced allow‑list-like behavior (only real `_action` methods should run).

**Severity:** High

---

## 2. Unsanitized `action` parameter used to build a dynamically invoked method name

**Location:** `Controller::dispatch()` – `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default'; $actionMethod = "{$action}_action";`

**OWASP Category:** A03:2021 – Injection (CWE‑470, Unsafe dynamic method invocation)

**Problem:**
The legacy code sanitized both controller and action names with `preg_replace("/[^A-Za-z0-9_]/", "", ...)` before using them to build class/method names. The new `dispatch()` performs **no sanitization** of `action` before concatenating it into a method name and calling it dynamically (`$controllerObj->$method(...)`). Combined with Issue 1 (the broken `is_callable` guard), this means arbitrary attacker-controlled strings are used to construct and invoke method names with no allow‑list of legitimate actions, relying entirely on PHP/Smarty's magic-method fallback to "fail safely" — which it does not, since the fallback is masked by `is_callable()` always returning `true`.

**Severity:** High (compounds Issue 1)

---

## 3. Incomplete / inconsistent centralized access control

**Location:** `Controller::CONTROLLER_ACL_MAP`, `checkControllerAcl()`, `dispatch()`

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:**
Only two controllers (`practice_settings`, `prescription`) have centrally enforced ACL checks. The remaining whitelisted controllers — `document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner` — have **no ACL enforcement whatsoever** in `Controller::dispatch()`. Access control for these depends entirely on each individual `C_*` controller class performing its own checks (as seen in `C_PracticeSettings`'s constructor). This pattern is fragile: it is easy for a future controller to be added to `VALID_CONTROLLERS` without ever implementing (or correctly implementing) its own ACL check, silently exposing data (documents, insurance info, HL7 messages, pharmacy data) to unauthorized users. Nested dispatch calls (e.g., `C_PracticeSettings::pharmacy_action()` creating a new `Controller` and calling `dispatch()` directly) bypass the parent's ACL context and re-enter `checkControllerAcl('pharmacy')`, which is a no‑op.

This refactor was an opportunity to centralize access control (as recommended by OWASP) but instead preserves/extends a scattered enforcement model.

**Severity:** Medium (High if any of the un-mapped controllers do not perform their own checks — needs verification against the actual `C_Document`, `C_Hl7`, `C_Pharmacy`, etc. source, which is not included).

---

## 4. State-changing action can be triggered via GET (CSRF-prone design), pre-existing but preserved

**Location:** `dispatch()`:
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```

**OWASP Category:** A01:2021 – Broken Access Control / CSRF

**Problem:**
Simply including a `process` key in the query string (GET) flips `$_POST['process']` to `"true"`, which later causes `"{$action}_action_process"` to execute — the method that normally performs the actual data-modifying work (e.g., writing a prescription, saving practice settings). There is no CSRF token validation visible anywhere in this flow. An attacker could craft a link such as:
`controller.php?controller=prescription&action=xyz&process=1&...`
and, if a logged-in clinician clicks it, trigger the processing branch without any state-changing confirmation step, enabling classic CSRF against sensitive medical/prescription data. This behavior is carried over unchanged from the pre-existing code, but since this PR rewrites and re-centralizes the dispatch logic, it was an opportunity to add CSRF protection that was not taken.

**Severity:** High

---

## 5. Information disclosure via exception messages

**Location:** `dispatch()` — `throw new BadRequestHttpException(...)`, `throw new NotFoundHttpException(...)`, and `AccessDeniedHelper::denyWithTemplate(...)` messages embed internal class/controller/ACL names.

**OWASP Category:** A05:2021 – Security Misconfiguration

**Problem:**
Exception messages include internal implementation details (`"Unable to load controller: $className"`, ACL section/value names). This is only a concern if these exceptions are not caught by a generic error handler and are rendered to the end user (stack traces, raw messages). This needs verification against the global exception/error handling configuration, since it is not shown in the diff.

**Severity:** Low (contingent on error-handling configuration elsewhere)

---

## 6. No security logging around ACL denial / invalid controller or action attempts

**Location:** `dispatch()`, `checkControllerAcl()`

**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures

**Problem:**
Failed ACL checks, invalid controller names, and invalid/nonexistent actions all result in exceptions or `AccessDeniedHelper` calls, but there is no explicit audit/security logging call added here to record repeated unauthorized access attempts (e.g., brute forcing controller/action names). Given this is the central request router for several sensitive modules (prescriptions, insurance, documents), logging unauthorized attempts would materially help detection of abuse.

**Severity:** Low

---

## 7. Positive note (not a vulnerability)

Replacing the previous "regex‑sanitize the user-supplied name, then dynamically build and load `C_$name.class.php`" pattern with a hardcoded whitelist (`VALID_CONTROLLERS`) for selecting the controller class/file is a **good security improvement** — it removes any realistic path to arbitrary file inclusion or arbitrary class instantiation based on user input for the controller name.

---

## 8. Pre-existing code touched by this change — worth re-verifying

**Location:** `controllers/C_PracticeSettings.class.php`
```php
$this->assign("FORM_ACTION", OEGlobalsBag::getInstance()->get('webroot') . "/controller.php?" . attr($_SERVER['QUERY_STRING']));
```

**OWASP Category:** A03:2021 – Injection (Reflected XSS) — contingent

**Problem:**
`$_SERVER['QUERY_STRING']` (fully attacker-controlled) is reflected back into an HTML attribute, mitigated only by `attr()`. This is unchanged by the diff, but since `C_PracticeSettings` is now routed through the new `dispatch()`/whitelist mechanism, it's worth re-confirming `attr()` performs full, context-correct escaping (including characters like `"`, `<`, `>`, and not just `&`-encoding), since this value is now reachable through additional code paths (nested `dispatch()` calls from sibling actions).

**Severity:** Low/Informational (contingent on `attr()`'s implementation, not shown)

---

## Summary

The refactor is a reasonable modernization (whitelist-based routing, explicit `controller`/`action` params, ACL map), but it introduces two **High severity regressions**:

1. The loss of the `method_exists()` check (needed because of Smarty's `__call()`), which effectively disables the "unknown action" rejection path and allows unsanitized, attacker-controlled strings to be used as dynamically invoked method names.
2. Removal of character sanitization on the `action` parameter that previously existed.

It also **perpetuates** two pre-existing, higher-risk design issues that deserve attention given they are directly exercised by this code:

3. Inconsistent/fragmented ACL enforcement across controllers (most controllers rely on self-enforced, unverified ACL checks).
4. A GET-parameter (`process`) that silently triggers state-changing POST-processing logic with no visible CSRF protection.

Lower-severity items relate to error-message information disclosure and lack of security event logging for access-control failures.