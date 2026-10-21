# Security Review: `Controller.class.php` Dispatch Refactor

## Finding 1 — Reintroduced `is_callable()`-only check bypasses Smarty's magic `__call()` guard
**Location:** `dispatch()`, process/action invocation block:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... }
```
**OWASP category:** A01:2021 – Broken Access Control / A04:2021 – Insecure Design

**Problem:** The original code explicitly documented and fixed this exact issue:
> "can no longer rely on is_callable since smarty 4 invokes a `__call` function deep within its classes, thus `is_callable()` is always true. so need to do both the `is_callable` and a `method_exists()` check."

The new `dispatch()` drops the `method_exists()` check entirely. Because `Controller extends Smarty`, and Smarty 4 defines a catch‑all `__call()`, `is_callable()` will return `true` for *any* method name — valid or not. This means:
- The "does the action method exist" check is effectively meaningless; any crafted `action` value will pass the `is_callable` gate and be invoked, routing into Smarty's internal `__call()` machinery with attacker-influenced method names and arguments.
- Additionally, when `$isProcessing` is true, the action method is called unconditionally (`$isProcessing || is_callable(...)`) even if it doesn't really exist, which can throw uncaught errors/exceptions from deep inside the Smarty library.

**Severity:** High — this is a direct regression of a previously-fixed security-relevant bug, and expands the dynamic dispatch attack surface.

---

## Finding 2 — `action` parameter is no longer sanitized before use
**Location:** `dispatch()`:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
...
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```
**OWASP category:** A03:2021 – Injection (reflected XSS potential) / A04:2021 – Insecure Design

**Problem:** The old code filtered the action name with `preg_replace("/[^A-Za-z0-9_]/", "", ...)` before using it. That filtering has been removed. Now:
- `$action` is used raw to build a dynamically-called method name (compounds Finding 1).
- `$action` is interpolated unescaped into an exception message. If this message is ever rendered to a browser (e.g., in a dev/debug error page or an unencoded error template), this is a reflected XSS vector, since `$action` comes directly from user-controlled request parameters.

**Severity:** Medium–High (depends on how exceptions are rendered downstream; should be verified).

---

## Finding 3 — CSRF-prone "process" flag (pre-existing, but reachable through the modified code path)
**Location:** `dispatch()`:
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
...
$isProcessing = ($_POST['process'] ?? '') === 'true';
```
**OWASP category:** A01:2021 – Broken Access Control (CSRF)

**Problem:** A state-changing "`_action_process`" method can be triggered purely by the presence of a `process` GET parameter — no CSRF token, no enforcement that the request is actually a POST. An attacker can craft a simple link/image/form that causes an authenticated user's browser to issue a GET request with `?process=1`, triggering process logic (e.g., prescription processing, document actions) without consent. This logic is carried over unchanged, but since this PR rewrites the surrounding dispatch logic, it's an appropriate point to flag it.

**Severity:** Medium–High, depending on what each controller's `_action_process` method does.

---

## Finding 4 — Positional argument binding from attacker-controlled parameter order
**Location:** `dispatch()`:
```php
foreach ($params as $key => $value) {
    if (in_array($key, $reservedParams, true)) continue;
    $args[$key] = $value === '' ? null : $value;
}
...
$result = $controllerObj->$method(...array_values($args));
```
**OWASP category:** A04:2021 – Insecure Design

**Problem:** Arguments are passed to controller action methods positionally, based on the iteration order of `$params`. Since `$params` typically originates from `$_GET`/`$_REQUEST`, and PHP preserves the order of keys as supplied in the query string, an attacker controls the order in which values are bound to the target method's parameters. This can cause parameter confusion (e.g., a value intended for `$doc_id` landing in `$patient_id`), bypassing expected validation assumptions in controller methods. This design flaw is inherited from the legacy `act()` method but is preserved/extended into the new, supposedly more robust `dispatch()`.

**Severity:** Low–Medium.

---

## Finding 5 — Centralized ACL enforcement only covers 2 of 10 whitelisted controllers
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`

**OWASP category:** A01:2021 – Broken Access Control

**Problem:** Only `practice_settings` and `prescription` have ACL checks enforced centrally. The remaining eight controllers (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) presumably perform their own ACL checks inside each controller class — this cannot be verified from this diff. Centralizing *some* but not *all* access checks here is risky: any new controller added to `VALID_CONTROLLERS` in the future, without a corresponding internal ACL check, would have no access control at all (pre-existing risk pattern, but worth flagging explicitly since this file is the chokepoint for all controller dispatch).

**Severity:** Medium (needs verification against each controller implementation).

---

## Finding 6 — Potential information disclosure via exception messages, and no security logging
**Location:** `dispatch()` throw statements (`BadRequestHttpException`, `NotFoundHttpException`)

**OWASP category:** A05:2021 – Security Misconfiguration / A09:2021 – Security Logging and Monitoring Failures

**Problem:**
- Exception messages include internal class/action names (`"Unable to load controller: $className"`, `"Action '$action' does not exist on controller: $className"`). If the global exception handler is misconfigured to show stack traces/details in production, this could aid reconnaissance.
- There is no explicit security logging of denied ACL checks, invalid controller names, or unknown action attempts in this dispatcher — such probing attempts (e.g., iterating through action names) would go unnoticed without log instrumentation.

**Severity:** Low.

---

## Summary Table

| # | Location | OWASP Category | Severity |
|---|----------|-----------------|----------|
| 1 | `dispatch()` is_callable-only checks | A01 / A04 | High |
| 2 | Unsanitized `$action` in method name & exception message | A03 (XSS) / A04 | Medium–High |
| 3 | `process` GET→POST flag | A01 (CSRF) | Medium–High |
| 4 | Positional argument binding | A04 | Low–Medium |
| 5 | Incomplete centralized ACL map | A01 | Medium (verify) |
| 6 | Exception detail / missing logging | A05 / A09 | Low |

**Overall recommendation:** Reinstate `method_exists()` alongside `is_callable()` for both action and process method checks (Finding 1 is the most urgent — it's a direct regression of a previously fixed issue). Re-apply strict whitelist sanitization (`[A-Za-z0-9_]`) to the `action` parameter before using it in dynamic dispatch or error messages. Add a proper CSRF token check for `_process` actions rather than relying on a bare `process` parameter. Confirm (and ideally centralize) ACL enforcement for all ten whitelisted controllers, not just two.