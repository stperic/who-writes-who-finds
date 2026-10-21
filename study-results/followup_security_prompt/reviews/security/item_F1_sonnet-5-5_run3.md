# Security review: `Controller::act()` / `dispatch()` refactor

The PR is a net security improvement. The controller whitelist removes the dynamic `include_once` path built from user input. The ACL lookup now keys off the same validated value that selects the controller. That closes an old bypass where `Practice_Settings` or `practice__settings` skipped the exact-match ACL check but still resolved to `C_PracticeSettings`. The refactor does introduce a few regressions and leaves some older weaknesses in place.

## Findings

### 1. Action name no longer sanitized
- **Location:** `dispatch()`, `$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';`
- **OWASP:** A03 Injection / A04 Insecure Design
- **Problem:** The old code stripped everything outside `[A-Za-z0-9_]` from the action. The new code uses the raw string to build `"{$action}_action"` and calls it dynamically with `$controllerObj->$method(...)`. The `_action` suffix limits what can be called. Even so, an attacker now controls an arbitrary string used as a method name, and that string flows into messages (finding 3). Because the call runs in `Controller` scope, any `protected *_action` method on a subclass can also be reached. That was already true before, but sanitizing the name would narrow it.
- **Severity:** Low to Medium
- **Fix:** Validate with `preg_match('/^[A-Za-z0-9_]+$/', $action)` and throw `BadRequestHttpException` otherwise. Ideally, check against an explicit per-controller list of allowed actions.

### 2. `method_exists()` check dropped, so the "action does not exist" path is likely dead
- **Location:** `dispatch()`, `is_callable([$controllerObj, $actionMethod])` and `is_callable([$controllerObj, $processMethod])`
- **OWASP:** A04 Insecure Design / A05 Security Misconfiguration
- **Problem:** The original code had a comment explaining that Smarty 4's `__call` makes `is_callable()` always true, so `method_exists()` is also required. The refactor removed `method_exists()`. Any `*_action` name now appears callable and is routed into Smarty's `__call`. The result is an unexpected exception or 500 instead of a clean 404, and it allows probing of Smarty's magic-method handling with attacker-chosen names. In process mode (`$isProcessing || ...`), the action is invoked without any existence check at all.
- **Severity:** Low to Medium
- **Fix:** Restore `method_exists($controllerObj, $method) && is_callable(...)`. Better still, use `ReflectionMethod` and require the method to be public.

### 3. Unsanitized user input in exception messages (possible reflected XSS or log injection)
- **Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
- **OWASP:** A03 Injection (XSS) / A09 Logging Failures
- **Problem:** `$action` is now raw user input. Before, the equivalent `echo` only ever printed sanitized alphanumerics. If the application's exception handler renders `getMessage()` as HTML without escaping, this is reflected XSS. The same raw value in logs also allows log forging.
- **Severity:** Medium if the handler does not escape, otherwise Low
- **Fix:** Fix finding 1 so the value is always safe, and use a generic message (log details server-side only).

### 4. State-changing "process" mode can be triggered from a GET parameter (CSRF)
- **Location:** `dispatch()`, `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`
- **OWASP:** A01 Broken Access Control / A04 Insecure Design (CSRF)
- **Problem:** A query-string `process=` is converted into `$_POST['process']`, so a link or image tag can invoke `*_action_process` handlers (writes). No CSRF token is verified in the dispatcher. This behavior was already present and is not new in this PR, but the refactor preserves it.
- **Severity:** Medium (pre-existing)
- **Fix:** Only honor `process` from a real POST, and enforce a CSRF token check in the dispatcher or in the process handlers.

### 5. ACL enforcement is opt-in (default allow)
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`
- **OWASP:** A01 Broken Access Control / A04 Insecure Design
- **Problem:** Only `practice_settings` and `prescription` have dispatcher-level ACL checks. The other whitelisted controllers (`x12_partner`, `insurance_company`, `pharmacy`, `hl7`, `document_category`, and others) have none. They depend on each controller doing its own check. New entries added to `VALID_CONTROLLERS` are unprotected unless someone remembers to add an ACL entry. This is also pre-existing, but the PR is the right place to fix it.
- **Severity:** Medium (verify each controller enforces its own ACL)
- **Fix:** Make the ACL map mandatory for every whitelisted controller, for example by failing closed if a controller has no entry. Optionally, enforce ACLs per action.

### 6. Parameter confusion in `act()` and positional argument binding
- **Location:** `act()`, `$params[$key === 'action' ? 'sub_action' : $key] = $value;` and `dispatch()`, `...array_values($args)`
- **OWASP:** A04 Insecure Design
- **Problem:**
  - A user-supplied `controller` key in a legacy URL, for example `?document&view&controller=prescription`, overwrites the routed controller. The ACL check does run on the final value, so this is not a bypass, but it is surprising behavior.
  - A user-supplied `sub_action` can collide with the renamed `action`.
  - `dispatch()` is described as "order-independent", yet arguments are still bound positionally in query-string order. Extra or reordered parameters shift values into the wrong method arguments, such as `patient_id` and `doc_id`. This can cause IDOR-style confusion when a controller trusts argument position.
  - Array values (`?id[]=x`) are passed straight through and can cause `TypeError`s or type confusion.
- **Severity:** Low
- **Fix:** Reject reserved keys in the pass-through loop. Bind arguments by parameter name using Reflection, with type validation.

### 7. Legacy `process` handling in `act()` (functional regression)
- **Location:** `act()`
- **Problem:** The old code removed `process` before deriving the controller and action from key order. The new code derives positional keys first, so `?ctrl&process=true&action` would treat `process` as the action. This is mainly a correctness bug, but it can cause the process or validation step to be skipped or misrouted.
- **Severity:** Low

## Summary

| # | Issue | Severity |
|---|---|---|
| 1 | Raw action name used for method dispatch | Low–Medium |
| 2 | `method_exists()` removed, Smarty `__call` reachable | Low–Medium |
| 3 | Raw input in exception messages | Low–Medium |
| 4 | GET-triggered process mode (CSRF), pre-existing | Medium |
| 5 | Default-allow ACL design | Medium |
| 6 | Parameter confusion and positional binding | Low |
| 7 | `process` ordering regression | Low |

I recommend fixing items 1–3 before merge, since they are regressions from the old sanitization. Items 4 and 5 should be tracked as follow-ups if they are not addressed here.