# Security Review: `Controller.class.php` routing refactor

## Summary

The refactor improves security in one key way. Replacing regex-sanitized dynamic class names with a fixed `VALID_CONTROLLERS` whitelist removes any chance of arbitrary file inclusion or class instantiation.

However, it also removes two defenses on the **action** side:
- the `[A-Za-z0-9_]` sanitization
- the `method_exists()` check

The removed comment explicitly said `method_exists()` was required because Smarty 4's `__call` makes `is_callable()` always return true. I recommend fixing Finding 1 before merging.

---

## Finding 1: Action name no longer validated; `method_exists()` guard removed

**Location:** `dispatch()`, in the `$action` / `$actionMethod` / `$processMethod` construction and the `is_callable(...)` checks.

**OWASP:** A03 Injection (unvalidated input used as a dynamic method name), A04 Insecure Design

**Severity:** Medium

**Problem:**

1. **Sanitization removed.** The old code ran `preg_replace("/[^A-Za-z0-9_]/", "", ...)` on the action. The new code takes `$params['action']` (attacker-controlled `$_GET`) and builds `"{$action}_action"` directly.

2. **`method_exists()` removed.** The deleted comment stated:
   > "smarty 4 invokes a __call function deep within its classes, thus is_callable() is always true. so need to do both the is_callable and a method_exists() check."

   The new code checks only `is_callable()`. As a result, `is_callable([$controllerObj, $actionMethod])` is always true. Any action name that does not match a real method is sent to Smarty's magic `__call` → `ext->_callExternalMethod()`.

3. **What the magic handler does.** It parses `set*`/`get*` method names into property names and reads or writes those properties on the object. It also tries to resolve and autoload `Smarty_Internal_Method_*` extension classes from the name.

   Example: `?controller=document&action=setCurrent` resolves to `setCurrent_action`. This maps to the `_current_action` property and sets it to the first query argument.

   The current impact is limited because of the forced `_action` suffix. Still, this hands an attacker-shaped method name to a third-party magic dispatcher that was never meant to be a routing target. Any future Smarty change or new property ending in `_action` widens the exposure.

4. **The "not found" path is effectively dead.** Unknown actions no longer reach the `NotFoundHttpException` branch. They fall into Smarty's handler instead, which throws `SmartyException`-style errors that may leak internals (see Finding 2).

**Fix:**
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
if (!preg_match('/^[A-Za-z0-9_]+$/', $action)) {
    throw new BadRequestHttpException("Invalid 'action' parameter");
}
$actionMethod  = "{$action}_action";
$processMethod = "{$actionMethod}_process";

$isRealPublicMethod = static function (object $obj, string $m): bool {
    if (!method_exists($obj, $m)) {
        return false;
    }
    $r = new \ReflectionMethod($obj, $m);
    // Must be public, non-static, and not inherited from Smarty
    return $r->isPublic() && !$r->isStatic()
        && !is_a($r->getDeclaringClass()->getName(), \Smarty::class, true)
            || is_subclass_of($r->getDeclaringClass()->getName(), \Smarty::class)
            && $r->getDeclaringClass()->getName() !== \Smarty::class;
};
```

At minimum:
- Restore `method_exists()` alongside `is_callable()` for both `$processMethod` and `$actionMethod`.
- When `$isProcessing` is true, do not call `$actionMethod` unconditionally without that check.

---

## Finding 2: Unsanitized input reflected in exception messages

**Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");` (and errors surfaced by Smarty's `__call` for bad method names).

**OWASP:** A03 Injection (reflected XSS), A05 Security Misconfiguration (information disclosure)

**Severity:** Low–Medium (depends on how uncaught exceptions are rendered)

**Problem:**
- The old code echoed `$c_action`, but only after stripping it to `[A-Za-z0-9_]`.
- The new message embeds raw `$_GET['action']`.
- If the exception message is rendered as HTML, this is reflected XSS. That happens with `display_errors` on, a debug or legacy error handler, or a page that prints `$e->getMessage()`.
  - Example payload: `?controller=document&action=<script>...</script>`
- Exception messages and stack traces may also reveal file paths and class names.

**Fix:**
- Validate `action` as in Finding 1. This alone removes the XSS vector.
- Avoid echoing user input in exception messages, or escape it wherever messages are displayed (`text()` / `attr()` in OpenEMR).
- Ensure production error handling does not render exception messages to users.

---

## Finding 3 (pre-existing, preserved): State-changing "process" actions can be triggered via GET

**Location:** `dispatch()`, in the "Handle process flag" block (`$_POST['process'] = "true"` when `process` is in the query string).

**OWASP:** A01 Broken Access Control (CSRF), A04 Insecure Design

**Severity:** Medium (pre-existing; not introduced by this PR)

**Problem:**
- A plain GET such as `controller.php?controller=prescription&action=edit&process=true&...` is promoted to a "process" (write) request.
- This calls `*_action_process` methods, which change data (prescriptions, pharmacies, insurance companies, etc.).
- GET requests can be triggered cross-site (e.g., via `<img src>`), and CSRF tokens are typically only checked on real POST bodies.

The new public `dispatch()` API, documented as the preferred entry point, carries this forward.

**Fix:**
- Require an actual `POST` with a valid CSRF token (`CsrfUtils::verifyCsrfToken`) before invoking any `_process` method.
- Drop the GET-to-POST promotion. If legacy links depend on it, gate it behind CSRF verification.

---

## Finding 4 (pre-existing, design): ACL map is allow-by-default

**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`

**OWASP:** A01 Broken Access Control

**Severity:** Low–Medium (no regression; behavior matches the old code)

**Problem:**
- Only `practice_settings` and `prescription` have ACL requirements.
- `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, `hl7`, `document_category`, and `patient_finder` are all directly addressable.
- These are normally reached as sub-controllers of `practice_settings`, which is protected by `admin/practice`. Calling them directly (e.g., `?controller=x12_partner&action=edit&process=true`) bypasses the parent's ACL unless each controller checks it itself.
- `checkControllerAcl()` silently returns when a controller is missing from the map. Any controller added to the whitelist later is therefore unprotected by default.

**Fix:**
- Now that there is a central whitelist, make ACL mandatory: every `VALID_CONTROLLERS` entry should have an ACL entry, and missing entries should deny by default.
- Give the admin sub-controllers the same `admin/practice` requirement as their parent. `document` and `patient_finder` should get appropriate `patients/*` checks if they lack internal ones.

---

## Minor observations (low / informational)

**`controller` key override in `act()`**
- A later query key literally named `controller` overwrites the positional controller (e.g., `?pharmacy&list&controller=prescription`).
- The ACL is checked against the controller actually dispatched, so this is not an ACL bypass. It does mean the legacy first-key semantics are no longer authoritative.
- Consider skipping or renaming a `controller` key in the loop, as is already done for `action`.

**Array values passed as arguments**
- Values such as `?foo[]=x` are now passed straight into action methods via `array_values($args)` with no type normalization. This was largely true before as well.
- Controllers expecting scalars may misbehave. Consider rejecting non-scalar values unless a method explicitly expects arrays.

**Positive change**
- The whitelist plus fixed `C_*` class names removes the dynamic include/instantiation surface of the old `i_once(... "/controllers/C_" . $c_name ...)`.

---

## Recommendation

**Request changes.** Restore action-name validation and the `method_exists()` guard (Finding 1), which also resolves the XSS vector in Finding 2. Strongly consider addressing Findings 3 and 4 while this routing layer is being redesigned, since `dispatch()` is positioned as the new standard entry point.