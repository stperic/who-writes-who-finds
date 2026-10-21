# Security Review: `library/classes/Controller.class.php`

## Finding 1 — Reintroduced unsafe dynamic method dispatch (dropped `method_exists()` guard)
**Location:** `Controller::dispatch()`, the `is_callable([$controllerObj, $processMethod])` / `is_callable([$controllerObj, $actionMethod])` checks, and the `$callMethod` closure.

**OWASP Category:** A04:2021 – Insecure Design (borders on A01 – Broken Access Control / potential RCE-adjacent issue)

**Problem:** The old code had an explicit, well-documented safeguard:

```php
// can no longer rely on is_callable since smarty 4 invokes a __call function deep within
// its classes, thus is_callable() is always true. so need to do both the is_callable
// and a method_exists() check.
```

and correspondingly checked `is_callable(...) && method_exists(...)`. The new `dispatch()` only checks `is_callable()`. Since `Controller extends Smarty`, and Smarty implements `__call()`, `is_callable()` on an arbitrary `{$action}_action` string will now almost always return `true` even when no such method exists, causing the real call to fall through into Smarty's magic `__call()` with **attacker-controlled method name and arguments**. This is exactly the regression the removed comment warned against. Depending on Smarty's `__call()` implementation this can lead to unintended method invocation, errors that leak internals, or worse.

Additionally, unlike the old code (`preg_replace("/[^A-Za-z0-9_]/", "", $c_action)`), the new `$action` value is used verbatim to build `$actionMethod`/`$processMethod` with **no character whitelist**, further widening the attack surface for this magic-method path.

**Severity:** High

---

## Finding 2 — Unsanitized `action` parameter stored/propagated without validation
**Location:** `dispatch()`: `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';` and `$controllerObj->_current_action = $action;`

**OWASP Category:** A03:2021 – Injection (reflected XSS potential) / A04 – Insecure Design

**Problem:** Previously, the action token was restricted to `[A-Za-z0-9_]` before use. Now arbitrary strings (including quotes, `<script>`, etc.) can flow into `_current_action`, which is a public property later consumed elsewhere (e.g., `_link()`), and is used to build method names as noted in Finding 1. If this property is later echoed into HTML/templates without escaping, this becomes a straightforward reflected XSS vector. At minimum this is a loss of input validation that existed in the prior version.

**Severity:** Medium–High (depends on downstream use of `_current_action`)

---

## Finding 3 — Inconsistent/incomplete ACL enforcement across controllers
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** Only `practice_settings` and `prescription` have ACL checks defined. The other eight whitelisted controllers — `document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner` — have **no ACL enforcement at all** in this dispatcher. Several of these deal with PHI/financial data (documents, HL7 messages, insurance info, patient search). This mirrors the pre-existing behavior, but the refactor makes it trivial to add entries to `CONTROLLER_ACL_MAP`, and the PR did not take the opportunity to close this gap — worth flagging explicitly since it's now a centralized, easily-auditable (and easily-fixed) map.

**Severity:** Medium (pre-existing, but should be addressed given data sensitivity)

---

## Finding 4 — Attacker-controlled positional argument ordering
**Location:** `dispatch()`: `$args[$key] = ...` built by iterating `$params` in request order, then `$controllerObj->$method(...array_values($args))`

**OWASP Category:** A04:2021 – Insecure Design

**Problem:** Arguments are still passed to action methods *positionally*, with the position determined by the order keys appear in the (attacker-supplied) query string, since PHP preserves `$_GET` order. Despite the docblock claiming `dispatch()` provides "order-independent routing," this only applies to `controller`/`action` — all additional arguments remain order-dependent and fully attacker-controlled. This can cause parameter confusion (e.g., a boolean flag landing in a position expected to hold an ID) in downstream action methods.

**Severity:** Low–Medium

---

## Finding 5 — Information disclosure via exception messages
**Location:** `throw new NotFoundHttpException("Unable to load controller: $className")`, `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className")`, `throw new BadRequestHttpException(...)`

**OWASP Category:** A05:2021 – Security Misconfiguration

**Problem:** Internal class names and action names are embedded in exception messages. If these exceptions are not caught and sanitized by a global error handler (and instead rendered directly, e.g., in debug/dev mode), this discloses internal implementation details useful for further attacks.

**Severity:** Low

---

## Finding 6 — No logging of dispatch failures / suspicious input
**Location:** All new failure paths in `dispatch()` (invalid controller, missing action, ACL denial)

**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures

**Problem:** None of the failure branches (invalid controller key, unresolvable action, bad ACL) emit any audit/security log entry; they only throw exceptions. Repeated probing for valid controller/action names (enumeration) or ACL bypass attempts would go unnoticed without framework-level logging of these exceptions.

**Severity:** Low

---

## Positive note
The move from building class names via `preg_replace`-sanitized user input (`"C_" . $c_name`) to a **fixed whitelist** (`VALID_CONTROLLERS`) mapping user input to known-good class name suffixes is a solid improvement — it eliminates a prior class-name/file-path injection risk and should be preserved. The regression noted in Finding 1 should be fixed to retain that improvement's full benefit.