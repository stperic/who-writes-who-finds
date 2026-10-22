# Security Review: `Controller::act()` / `Controller::dispatch()` refactor

## Summary

The controller whitelist and centralized ACL map are improvements. They close the old `i_once()` path built from user input. But the new code drops two safeguards the old code had:

1. **Action-name sanitization.** The old code stripped the action to `[A-Za-z0-9_]`.
2. **The `method_exists()` check.** The deleted comment explained that Smarty 4's `__call()` makes `is_callable()` always return true.

Without these, the user controls the method name that gets invoked, and unknown names fall through to Smarty's internal magic dispatcher.

---

## Finding 1 – Unsanitized action name invokes arbitrary methods via Smarty `__call`

**Location:** `Controller::dispatch()`:
```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
$processMethod = "{$actionMethod}_process";
...
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
```

**OWASP:** A03 Injection, plus A01 Broken Access Control.

**Problem:**
- `$action` comes straight from `$_GET`. This happens through `act()` (second query key) or through a direct `controller=…&action=…` request.
- The old `preg_replace("/[^A-Za-z0-9_]/", "", …)` filter is gone.
- `Controller` extends `Smarty`, which defines `__call()`. So `is_callable()` is true for every method name, and the `method_exists()` guard was removed.
- Result: any string ending in `_action` (or `_action_process`) is called on the controller.
  - If the method really exists, it runs. This includes inherited or helper methods never meant to be routable.
  - If it does not exist, the request is forwarded into Smarty's `__call` / extension handler. That handler resolves the name to internal `Smarty_Internal_Method_*` classes and getter/setter logic, possibly triggering autoloading with attacker-influenced class names.
- Request arguments are spread positionally into whatever method is reached.
- The `else` branch that throws `NotFoundHttpException` can now never be reached. That is clear evidence the existence check is broken.
- The same issue hits sub-controller dispatch. In `C_PracticeSettings::*_action($arg)`, the raw query value `$arg` becomes the sub-controller action with no sanitization. The old `act()` call sanitized it.

**Severity:** High. The exact impact depends on Smarty internals, but this restores an unconstrained method-dispatch surface in an EHR application.

**Fix:**
- Validate `$action` with `preg_match('/^[A-Za-z0-9_]+$/', $action)`, or use a per-controller allowlist.
- Require `method_exists($controllerObj, $method)` before calling. Ideally also check through `ReflectionMethod` that the method is public and declared on the concrete controller class.

---

## Finding 2 – Processing path calls the action method without any existence check

**Location:** `if ($isProcessing || is_callable([$controllerObj, $actionMethod]))`

**OWASP:** A04 Insecure Design.

**Problem:**
- When `process=true` (from GET `process` or POST `process`), `$actionMethod` is called unconditionally, even if the method does not exist.
- This was also true in the old code, but there the name was sanitized.
- Combined with Finding 1, any `POST process=true` request goes straight into `__call` with an attacker-chosen name.

**Severity:** Medium (it amplifies Finding 1).

**Fix:** Apply the same `method_exists()` and name validation on both branches.

---

## Finding 3 – Unescaped user input in exception messages

**Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`

**OWASP:** A03 Injection (XSS) and minor information disclosure.

**Problem:**
- `$action` is raw user input placed into an exception message.
- If the global error handler or debug page renders exception messages as HTML, this is reflected XSS.
- It is currently unreachable because of Finding 1, but it will become reachable once Finding 1 is fixed with `method_exists()`.

**Severity:** Low.

**Fix:** Validate `$action` before building the message, use a generic message, or escape on output.

---

## Finding 4 – ACL map covers only 2 of 10 routable controllers (pre-existing, carried forward)

**Location:** `CONTROLLER_ACL_MAP`

**OWASP:** A01 Broken Access Control.

**Problem:**
- `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, `hl7`, `document_category`, `document`, and `patient_finder` have no central ACL entry.
- Most of these are presented as "Practice Settings" sub-pages. `C_PracticeSettings`'s constructor enforces `admin/practice` for them.
- However, they can also be reached directly, e.g. `controller.php?controller=x12_partner&action=edit` or `?insurance_company&edit`. Direct access skips the `practice_settings` check.
- Unless each controller enforces its own ACL (not visible in this diff), authenticated low-privilege users could view or modify X12 partners, insurance companies, and pharmacies.
- This existed before this change. The new whitelist is the natural place to fix it.

**Severity:** Medium (needs confirmation against each controller class).

**Fix:** Add ACL entries for every whitelisted controller. For example, map `admin/practice` to the practice-settings sub-controllers and the appropriate `patients/*` ACLs to `document` and `patient_finder`. Make "no entry" fail closed.

---

## Notes (not vulnerabilities)

- **`controller` override in `act()`.** In `act()`, a `controller=` query parameter overwrites the positional controller. This is benign because the whitelist lookup and ACL check use the final value.
- **Arrays as arguments.** Query parameters such as `foo[]=` are passed as arrays into action methods that expect scalars. This was pre-existing; consider normalizing argument types.