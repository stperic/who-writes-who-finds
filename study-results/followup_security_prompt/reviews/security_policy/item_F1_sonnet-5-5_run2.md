## Security review of `Controller.class.php` (`act()` / `dispatch()` refactor)

The refactor improves some things. The controller whitelist replaces filename construction from user input, which removes the old path/class-name injection surface. The ACL check now runs against the whitelisted value. But it also removes several defensive checks and leaves existing weaknesses in place.

### Findings

**1. Action name is no longer sanitized and is used for dynamic method invocation**
- **Location:** `dispatch()`, `$action = is_string($params['action'] ...)`, `$actionMethod = "{$action}_action"`, `$controllerObj->$method(...)`
- **OWASP:** A03 Injection / A04 Insecure Design
- **Problem:** The old code stripped everything outside `[A-Za-z0-9_]` from the action. The new code uses the raw request string to build a method name that is then called dynamically. The `_action` suffix limits what can be reached, but the attacker now controls arbitrary bytes in a dynamic method name. That includes names that hit Smarty's `__call`/extension-handler magic, since `Controller` extends Smarty. The `_action` suffix and the regex-based name resolution in Smarty make direct abuse unlikely but not provably impossible.
- **Fix:** Re-apply the allowlist regex, for example `^[A-Za-z0-9_]+$`, and reject anything else.
- **Severity:** Medium

**2. The `method_exists()` guard was removed, so `is_callable()` is now effectively always true**
- **Location:** `dispatch()`, `is_callable([$controllerObj, $processMethod])` and `is_callable([$controllerObj, $actionMethod])`
- **OWASP:** A04 Insecure Design / A05 Security Misconfiguration
- **Problem:** The original code had a comment explaining that Smarty 4's `__call` makes `is_callable()` always true, so it also required `method_exists()`. The new code drops that check. Consequences:
  - The `NotFoundHttpException` branch becomes dead code.
  - Any request with an arbitrary `action` reaches Smarty's magic `__call`, causing unhandled exceptions and possible stack-trace or information leakage.
  - Nonexistent process methods are "callable" and get invoked.
  - Methods that were never intended as endpoints are exposed to the attacker-controlled name.
- **Fix:** Restore `method_exists()` and, better, check that the method is public and declared on the controller class.
- **Severity:** Medium

**3. Attacker-controlled strings in exception messages (possible reflected XSS)**
- **Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className")` and the similar `BadRequestHttpException`/`NotFoundHttpException` messages
- **OWASP:** A03 Injection (XSS)
- **Problem:** `$action` is now raw user input, where it used to be sanitized before being echoed. If the exception handler renders the message into HTML without escaping, this is reflected XSS. Per finding 2, this branch is currently hard to reach, but it becomes reachable once the guard is fixed.
- **Fix:** Sanitize the action first, or don't include user input in the message. Verify that the renderer escapes output.
- **Severity:** Medium (depends on the renderer)

**4. Access control covers only two controllers**
- **Location:** `CONTROLLER_ACL_MAP`, `checkControllerAcl()`
- **OWASP:** A01 Broken Access Control
- **Problem:** Only `practice_settings` and `prescription` have ACL checks. Every other whitelisted controller (`document`, `insurance_company`, `insurance_numbers`, `pharmacy`, `x12_partner`, `hl7`, `patient_finder`, `document_category`) is reachable by any user who can reach this script, unless the individual controllers enforce ACLs themselves.
- **Related:** `pharmacy` is normally reached through `practice_settings`, but a direct `controller=pharmacy` request skips the `admin/practice` check. This was already the case in the old code, but the change touches this logic and preserves it.
- **Fix:** Use deny-by-default, with an ACL entry required for every controller, and per-action checks.
- **Severity:** High if the controllers don't self-check, otherwise Medium. This is pre-existing.

**5. State-changing "process" flag can be triggered via GET (CSRF)**
- **Location:** `dispatch()`, `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`
- **OWASP:** A01 Broken Access Control / A04 Insecure Design
- **Problem:** A `process` value in the query string is converted into a POST-style process request, so `*_action_process` handlers can be triggered by a cross-site link or image. The controller has no CSRF token check. This is pre-existing but preserved.
- **Fix:** Require POST and validate a CSRF token before running any `_process` method.
- **Severity:** Medium

**6. Parameter handling in `act()` and `dispatch()`**
- **Location:** `act()` parameter-merge loop, and `dispatch()` `array_values($args)` with `...` spread
- **OWASP:** A04 Insecure Design / A03 Injection
- **Problems:**
  - In `act()`, remaining keys are not checked against reserved names. A request like `?document&view&controller=pharmacy` overwrites `$params['controller']`, as does `process`. The whitelist and ACL check still run on the overwritten value, so this is not a direct bypass. It is still confusing, and it lets users change the routed controller away from the positional URL.
  - Arguments are bound by position from the arbitrary order and number of query parameters, not by name. Reordering or adding parameters changes which method argument receives which value, and attacker-supplied arrays (`id[]=...`) are passed straight into methods that expect scalars. This can cause type errors or injection if downstream code concatenates the values into SQL or HTML.
  - Arguments are never validated or typed.
- **Fix:** Bind arguments by name using reflection, reject reserved keys, and cast or validate types.
- **Severity:** Medium or Low

**7. Loosened state check (`== false` → `=== false`)**
- **Location:** `dispatch()`, `if ($controllerObj->_state === false)`
- **OWASP:** A04 Insecure Design
- **Problem:** The original used `== false`, which also matched `null`, `0` and `""`. A process handler that signaled failure or stopped processing with one of those values will now fall through into the main action. Examples include a failed validation, an authorization failure, or a redirect that should halt. This is a behavioral change in a control-flow security decision.
- **Fix:** Audit controllers that set `_state`, and normalize them to a boolean.
- **Severity:** Low to Medium

### Summary
The whitelist for controller selection is a clear improvement. Before merging, I would require three changes:
- Restore action-name sanitization and the `method_exists()` check.
- Stop reflecting raw input in exception messages.
- Use a deny-by-default ACL map, with CSRF protection on `process`.