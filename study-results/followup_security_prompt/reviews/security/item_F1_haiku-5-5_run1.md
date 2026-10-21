# Security Review: `library/classes/Controller.class.php`

The refactor adds a controller whitelist and moves ACL checks into a dedicated method, which improves on the original. Several regressions remain, the most important being that the sanitization of the action name was removed. Findings are below in rough priority order.

## Findings

### 1. Unsanitized action name reflected in exception message (possible XSS)
- **Location:** `dispatch()`, `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
- **OWASP category:** A03:2021 Injection (XSS)
- **Problem:** The original code built the error text from `$c_action`, which had been passed through `preg_replace("/[^A-Za-z0-9_]/", "", ...)`. The new code uses the raw `$action` from `$params['action']`. If the front controller or global exception handler renders the exception message as HTML without escaping, a request such as `controller.php?controller=document&action=<script>...</script>` produces reflected XSS. Whether this is exploitable depends on the exception handler, which is not in the diff.
- **Severity:** Medium (High if the handler renders messages unescaped on an authenticated page)
- **Recommendation:** Validate `$action` against `/^[A-Za-z0-9_]+$/` before use, and HTML-escape any user-derived text in error output.

### 2. Action name is no longer constrained before it becomes a method name
- **Location:** `dispatch()`, `$actionMethod = "{$action}_action"; $processMethod = "{$actionMethod}_process";`
- **OWASP category:** A03:2021 Injection; A04:2021 Insecure Design
- **Problem:** The old code stripped non-alphanumeric characters from the action name. The new code allows any string. Two consequences:
  - The `is_callable()` gate limits most calls to real public methods, but the comment in the original code notes that Smarty uses `__call` internally, so `is_callable()` can return true for names that have no real method behind them.
  - More seriously, the process branch is `if ($isProcessing || is_callable(...))`. When `process=true` is set, `$actionMethod` is invoked **without any existence check**. An attacker who sends `process=true&action=<anything>` reaches an unguarded dynamic method call. The original code had the same shape, but the new code should not carry it forward, especially since it now throws `NotFoundHttpException` elsewhere and is inconsistent about it.
- **Severity:** Medium
- **Recommendation:** Restore the alphanumeric/underscore validation on `$action`. Apply the `is_callable()` check to the action method in both branches, and throw `NotFoundHttpException` when it fails. Consider a per-controller allowlist of action methods.

### 3. Only two controllers have an ACL gate; the whitelist exposes the rest
- **Location:** `VALID_CONTROLLERS` and `CONTROLLER_ACL_MAP`; `checkControllerAcl()`
- **OWASP category:** A01:2021 Broken Access Control
- **Problem:** `document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner` and others are routable through `dispatch()`, but none has an ACL check at the router level. The original `act()` had the same gap, so this is not a regression. However, the diff now presents these as the sanctioned routing surface, so it is worth confirming that every `C_*` controller and each of its actions enforces its own ACL.
- **Severity:** Low (needs verification; High for any controller that lacks internal checks)
- **Recommendation:** Add an ACL entry for every whitelisted controller, or document that each controller must enforce ACL internally and verify that it does.

### 4. Explicit `controller` parameter can override the positionally routed controller in `act()`
- **Location:** `act()`, the loop `$params[$key === 'action' ? 'sub_action' : $key] = $value;`
- **OWASP category:** A04:2021 Insecure Design
- **Problem:** The loop skips only the positional controller key and the positional action key. An explicit `controller=` in the query string is copied into `$params` and overwrites the routed controller. For example, `?practice_settings&controller=prescription` routes to `prescription`, and the ACL check then runs against `prescription`. The ACL check and the loaded class are consistent, so this is not a direct bypass, but legacy URLs no longer mean what their positional key implies, and the ACL assumptions for the original key do not hold.
- **Severity:** Low
- **Recommendation:** In `act()`, reject or strip reserved keys (`controller`, `action`, `process`) from the legacy parameter set, or throw `BadRequestHttpException` when they conflict with the positional routing.

### 5. Positional argument passing from user-controlled order
- **Location:** `dispatch()`, `$controllerObj->$method(...array_values($args));`
- **OWASP category:** A04:2021 Insecure Design
- **Problem:** Arguments are passed positionally, so the order of query-string parameters determines which controller method parameter receives which value. Named parameters are discarded by `array_values()`. Values may also be arrays (for example `?x[]=...`), which can cause type confusion in methods that expect strings. The behaviour is the same as the original, but the new code makes it the documented routing contract.
- **Severity:** Low
- **Recommendation:** Pass arguments by name using reflection, or require controllers to read `$_GET`/`$_REQUEST` through typed accessors. Reject array values for scalar parameters.

### 6. Uncaught exceptions may expose internals
- **Location:** All `throw` statements in `dispatch()`; the original code used `echo` and `exit`
- **OWASP category:** A05:2021 Security Misconfiguration
- **Problem:** The router now throws Symfony HTTP exceptions instead of printing a message and exiting. If the caller does not catch them, the output depends on the application's error handler and `display_errors` configuration. It may include class names, file paths, or stack traces.
- **Severity:** Low
- **Recommendation:** Confirm that all callers of `dispatch()`/`act()` catch `HttpException` and return a generic response, and that production error display is disabled.

### 7. Legacy `act()` with empty input
- **Location:** `act()`, `$keys[0]`
- **OWASP category:** A05:2021 Security Misconfiguration (minor)
- **Problem:** The docblock requires `non-empty-array`, but there is no runtime guard. An empty array triggers an undefined-index warning, and warnings can leak paths when displayed.
- **Severity:** Informational
- **Recommendation:** Add an explicit empty check that throws `BadRequestHttpException`.

### 8. Pre-existing: GET parameter promotes to POST `process`
- **Location:** `dispatch()`, the `process` handling
- **OWASP category:** A01:2021 Broken Access Control (CSRF-related)
- **Problem:** `?process=...` in a GET request sets `$_POST['process']="true"`, so state-changing actions can be triggered by a GET link, which weakens CSRF protections. This behaviour is carried over from the original code.
- **Severity:** Informational (pre-existing)
- **Recommendation:** Require POST for `process` actions, and enforce CSRF token validation inside the process methods.

## Positive observations
- The controller name is resolved through a fixed whitelist, so the file path and class name cannot be attacker-controlled. Path traversal through `controller=` is not possible.
- The ACL check is applied to the resolved controller name, not the raw input.
- `array_values()` prevents named-argument injection through spread.
- Unknown controllers no longer echo the attacker-supplied name.

## Summary

| # | Location | Category | Severity |
|---|----------|----------|----------|
| 1 | `dispatch()` NotFound message | A03 XSS | Medium |
| 2 | `dispatch()` method name / process branch | A03 / A04 | Medium |
| 3 | ACL map coverage | A01 | Low (verify) |
| 4 | `act()` controller override | A04 | Low |
| 5 | Positional argument passing | A04 | Low |
| 6 | Exception exposure | A05 | Low |
| 7 | `act()` empty input | A05 | Informational |
| 8 | GET `process` promotion | A01 (CSRF) | Informational (pre-existing) |

**Recommendation:** Do not merge until findings 1 and 2 are fixed. The simplest fix for both is to restore strict validation of `$action` (`/^[A-Za-z0-9_]+$/`) and apply the `is_callable()` existence check consistently in both the process and non-process branches.