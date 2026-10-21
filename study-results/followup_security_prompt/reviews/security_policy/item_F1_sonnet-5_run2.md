# Security Review – `Controller.class.php` diff

## 1. Loss of input validation on the `action` parameter → unsafe dynamic method dispatch
**Location:** `dispatch()` —
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
$processMethod = "{$actionMethod}_process";
...
$result = $controllerObj->$method(...array_values($args));
```

**OWASP Category:** A03:2021 – Injection (CWE-470 Unsafe Reflection / unvalidated dynamic method call), overlapping with A04:2021 – Insecure Design.

**Problem:**
The legacy `act()` sanitized the action value before use:
```php
$c_action = preg_replace("/[^A-Za-z0-9_]/", "", (string) array_pop($args));
```
This whitelist (`[A-Za-z0-9_]`) is **gone** in the new code. `$action` now flows straight from `$_GET['action']`/`$_POST` into a string that is concatenated and used as a PHP method name (`$controllerObj->$method(...)`).

This is compounded by a second regression: the original code guarded the call with **both** `is_callable()` *and* `method_exists()`, because (per the original comment) Smarty 4's internal `__call()` makes `is_callable()` return `true` for *any* method name. The new code only checks `is_callable()`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... }
```
Since `is_callable()` is effectively a no-op here, **any attacker-supplied `action` string will reach the method call / `__call()` magic method**, with no character restrictions and no real existence check. Depending on what `__call()` does downstream in the Smarty class hierarchy, this can enable unintended method invocation, logic bypass, or (if any magic handler builds file/template paths from the method name) local file inclusion or template injection.

**Severity:** High — two independent, previously-existing security controls (character whitelist + `method_exists()` guard) were both removed in the same refactor, and the resulting input reaches a dynamic dispatch sink driven entirely by `$_GET`/`$_POST`.

**Recommendation:** Re-apply a strict whitelist (e.g. `preg_match('/^[A-Za-z0-9_]+$/', $action)`) and restore the `method_exists()` check (or better: validate against an explicit list of allowed action names per controller, consistent with the new `ControllerInterface`/whitelist approach already used for controller names).

---

## 2. GET-triggered "process" state change (inherited, still present)
**Location:** `dispatch()`:
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```

**OWASP Category:** A01:2021 – Broken Access Control / CSRF.

**Problem:** A plain `GET` request containing `process` in the query string is silently promoted to `$_POST['process'] = "true"`, causing "processing" (state-changing) action methods to run even though the request was not actually a form POST. There is no visible CSRF token check in this code path. This was present before the diff but is directly inside the code this PR rewrites, and it still gates execution of `_action_process` methods for sensitive controllers (e.g., `prescription`, `practice_settings`).

**Severity:** Medium (pre-existing, but worth flagging since it governs the authorization-sensitive "process" branch touched by this change).

---

## 3. Incomplete centralized ACL coverage
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()` vs. `VALID_CONTROLLERS`.

**OWASP Category:** A01:2021 – Broken Access Control.

**Problem:** Only `practice_settings` and `prescription` have centralized ACL checks. The other 8 whitelisted controllers (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) get **no** ACL enforcement from this dispatcher — they must perform all authorization internally (not visible in this diff). This mirrors the pre-existing design, but because this refactor formalizes a single routing chokepoint (`dispatch()`), it is a good opportunity to confirm each of those controllers enforces ACL on every action; otherwise this is a silent access-control gap.

**Severity:** Medium (pre-existing design issue, carried forward).

---

## 4. User-controlled values echoed into exception messages
**Location:**
```php
throw new BadRequestHttpException("Missing or invalid 'controller' parameter");
throw new NotFoundHttpException("Unable to load controller: $className");
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```

**OWASP Category:** A05:2021 – Security Misconfiguration (information exposure through error messages).

**Problem:** `$action` and `$className` are derived from (or close to) user input and are embedded verbatim in exception messages. If these exceptions are rendered to the end user (e.g., Symfony debug/dev pages, or a generic error handler that echoes `getMessage()`), this can leak internal structure or be used for enumeration of valid/invalid controller names. Not full XSS by itself, but should be sanitized/generalized in production error handling, and verified that the global exception handler does not reflect raw input back as HTML.

**Severity:** Low.

---

## 5. Argument binding depends on attacker-controlled key order
**Location:** `act()`/`dispatch()`:
```php
foreach ($params as $key => $value) { ... $args[$key] = ...; }
...
$controllerObj->$method(...array_values($args));
```

**OWASP Category:** A04:2021 – Insecure Design.

**Problem:** Arguments are passed positionally to the target action method based on the iteration order of `$params`, which in turn is derived from the raw order of `$_GET`/`$_POST` keys supplied by the client. This mirrors legacy behavior but is fragile: it makes correctness (and therefore security, if parameter order encodes meaning such as which ID is the "owner" record) dependent on client-supplied key ordering rather than explicit named binding.

**Severity:** Low.

---

## 6. Missing security logging around authorization/routing failures
**Location:** `checkControllerAcl()`, invalid controller/action branches in `dispatch()`.

**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures.

**Problem:** Neither failed ACL checks, nor invalid-controller requests, nor unknown-action requests generate an explicit audit/security log entry in this code (beyond whatever `AccessDeniedHelper::denyWithTemplate` does internally, which is unchanged). Repeated probing of controller/action names (a reconnaissance pattern enabled by point #1 above) would go unnoticed without such logging.

**Severity:** Low.

---

### Positive notes (not vulnerabilities, for context)
- Replacing dynamic class-name construction (`"C_" . ucfirst(...)`) with an explicit `VALID_CONTROLLERS` whitelist is a genuine improvement: it removes the previous (lower) risk of loading an unintended `C_*.class.php` file based on attacker input, since the class/file name is now fully determined by the whitelist rather than string concatenation of (regex-filtered) user input.
- Throwing typed HTTP exceptions instead of `echo`/`exit` is a better pattern, assuming the global exception handler does not leak stack traces/debug info in production (see item 4).

---

### Summary
The most significant issue is **#1** — the refactor silently drops both the character-whitelist sanitization and the `method_exists()` safety check that the original code relied on specifically because `is_callable()` is unreliable with Smarty's `__call()`. This turns the `action` query parameter into an effectively unvalidated dynamic dispatch target. This should be treated as the priority fix before merge. Items #2–#6 are secondary/pre-existing concerns worth tracking but are not blockers introduced solely by this diff.