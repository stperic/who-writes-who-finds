## Security review: `library/classes/Controller.class.php`

**Verdict: Do not merge as-is.** The change removes the old path-traversal exposure and adds a controller whitelist, but it weakens input validation on the action name, calls methods without the existence checks the old code had, and leaves ACL coverage thin. The findings below are ordered by severity.

---

### 1. Unvalidated action name reaches method invocation and output (Injection / Insecure Design)
**Location:** `dispatch()`, the `$action` assignment and `$actionMethod`/`$processMethod` construction, plus the `NotFoundHttpException` messages.

**Problem:** The old code sanitized the action with `preg_replace("/[^A-Za-z0-9_]/", "", ...)`. The new code takes `$params['action']` verbatim. Consequences:
- Any string becomes a method name (`"{$action}_action"`). PHP accepts arbitrary method names through variable dispatch, so the method-name space is no longer constrained to identifier characters.
- The raw value is interpolated into `NotFoundHttpException` messages (`"Action '$action' does not exist..."`). If the exception renderer emits HTML without escaping (for example in a debug or custom error page), this is reflected XSS. The old code avoided this because it sanitized input before echoing it.

**Severity:** Medium (High if the exception renderer does not escape output).

**Fix:** Validate `$action` against `/^[A-Za-z][A-Za-z0-9_]*$/` before building method names, and HTML-escape anything reflected in error output.

---

### 2. Method existence check skipped on the process path (Insecure Design / Broken Access Control)
**Location:** `dispatch()`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
```

**Problem:** When `$isProcessing` is true, the code calls `$actionMethod` without checking `is_callable`. The original code explicitly stated that `is_callable` alone is unreliable under Smarty 4, and paired it with `method_exists`. This version drops that check on the processing branch. Any name that reaches `__call` (including through Smarty's magic methods) or a non-public method may be invoked. Protected and private methods can also be reached, because the closure executes in `Controller` scope and the process branch skips the visibility check that `is_callable` applies from outside. Visibility is only partly enforced here.

**Severity:** Medium.

**Fix:** Use `method_exists()` plus a visibility check (for example `ReflectionMethod` with `isPublic()`) on both branches, and never call an unchecked name.

---

### 3. ACL coverage is limited to two controllers (Broken Access Control)
**Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`.

**Problem:** Only `practice_settings` and `prescription` are gated centrally. The other ten whitelisted controllers, including `pharmacy`, `insurance_company`, `insurance_numbers`, `hl7`, `x12_partner`, `document`, and `document_category`, rely entirely on checks inside each controller. The `practice_settings` ACL was designed to protect admin functions, and the `pharmacy` controller is part of that delegation chain (`practice_settings->pharmacy->list`). Calling `controller=pharmacy` directly skips the `admin/practice` requirement. The old code had the same gap, so this is pre-existing, but this change adds the controller to the whitelist and does not close it.

**Severity:** High, pending verification. Confirm that every whitelisted controller's actions check ACL themselves, and that `pharmacy` (and any other sub-controller reachable from `practice_settings`) enforces `admin/practice` directly.

---

### 4. Attacker-controlled parameters passed positionally (Insecure Design / Data Integrity)
**Location:** `dispatch()`, the `$args` build and `$callMethod` using `array_values($args)`.

**Problem:**
- Arguments are passed by position in query-string order, not by the action method's parameter names. The docblock says routing is "order-independent", which is inaccurate for argument binding. An attacker can reorder parameters to shift values into different positional slots, and can add extra parameters that get appended to the argument list.
- Array-valued parameters (`?doc_id[]=1`) are passed through unchanged. Functions expecting scalars will throw `TypeError`, and any code that does not validate types may act on unexpected structures.
- Empty values are converted to `null`, which may bypass the intended "required" checks in the callee if those checks use `isset` rather than explicit validation.

**Severity:** Low to Medium, depending on how the action methods validate their inputs.

**Fix:** Bind arguments by name using reflection (`ReflectionMethod::getParameters()`), reject unknown parameters, and cast or reject non-scalar values before the call.

---

### 5. Process flag can be set through GET, enabling state-changing actions via link (CSRF) (Broken Access Control)
**Location:** `dispatch()`, the `process` handling:
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```

**Problem:** `$params` typically comes from `$_GET`, so a crafted link such as `controller.php?controller=...&action=...&process=true` triggers `_action_process` handlers. Those handlers perform state changes, and the link can be delivered cross-site with no token. The `isset` check also accepts any value, including `process=false`. Writing into `$_POST` mutates a superglobal and mixes request sources, which makes the flow harder to reason about. This behavior existed before, but the rewrite keeps it and widens it because `isProcessing` now reads `$_POST` after a GET-derived assignment.

**Severity:** Medium (depends on whether the `_process` handlers verify a CSRF token; verify this).

**Fix:** Accept `process` only from POST, require an explicit `=== 'true'` value, and require a CSRF token on all `_process` actions.

---

### 6. Unhandled exceptions may expose internals (Security Misconfiguration / Logging)
**Location:** `dispatch()` throws `BadRequestHttpException` and `NotFoundHttpException`; `act()` now returns `dispatch()`'s result.

**Problem:** The old code echoed a message and called `exit`. The new code throws. Legacy callers of `act()` (for example `controller.php`) may not catch these, so they reach the global handler. Depending on configuration, this can produce stack traces with file paths and class names. Controller class names are also exposed in messages. No logging is added for rejected or denied requests.

**Severity:** Low.

**Fix:** Catch these exceptions at the entry point, return generic 400/404 responses, log details server-side, and confirm debug mode is off in production.

---

### 7. Legacy routing misparses an explicit `action` key (Functional / Insecure Design)
**Location:** `act()`.

**Problem:** For a URL such as `controller.php?document&action=view`, `$keys[1]` is `'action'`, so `$positionalAction` becomes `'action'`. The loop then skips that key, and the call resolves to `action_action` rather than `view_action`. This is a correctness bug, not directly exploitable, but it can cause unexpected method calls and makes the routing hard to audit.

**Severity:** Low.

---

### Summary

| # | Issue | OWASP category | Severity |
|---|-------|----------------|----------|
| 1 | Unvalidated action name; reflected in errors | A03 Injection / A04 Insecure Design | Medium (High if unescaped) |
| 2 | Unchecked method invocation on process path | A01 Broken Access Control / A04 | Medium |
| 3 | Limited ACL coverage; `pharmacy` bypasses admin ACL | A01 Broken Access Control | High (verify) |
| 4 | Positional, attacker-ordered argument binding | A04 Insecure Design / A08 Integrity | Low–Medium |
| 5 | `process` flag via GET enables state-changing requests without CSRF protection | A01 / A04 | Medium (verify) |
| 6 | Exceptions may leak internals; no security logging | A05 Misconfiguration / A09 Logging | Low |
| 7 | Legacy `action` key misrouting | Functional / A04 | Low |

**Positive changes:** The controller whitelist (`VALID_CONTROLLERS`) removes the previous arbitrary file include and class instantiation, and the file path is now built only from whitelisted values.