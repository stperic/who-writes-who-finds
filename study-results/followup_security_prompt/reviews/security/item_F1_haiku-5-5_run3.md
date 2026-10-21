# Security Review: `Controller.class.php` routing refactor

**Verdict:** No critical or high-severity issues. The whitelist for `controller` is a real improvement over the old regex-sanitized class-name construction. I found one medium-severity regression in method dispatch and several lower-severity issues.

---

### 1. Dynamic method dispatch with weakened checks (regression)
- **Location:** `dispatch()`, the `$processMethod`/`$actionMethod` block, `$callMethod`
- **OWASP:** A03:2021 Injection (dynamic invocation), A04:2021 Insecure Design
- **Problem:**
  - `$action` comes directly from the request and is concatenated into a method name (`"{$action}_action"`). It is never validated against an identifier pattern. The old code stripped characters with `preg_replace`, and this new code does not.
  - The old code checked both `is_callable()` and `method_exists()`. The old comment explains why: Smarty 4's `__call` makes `is_callable()` always true. The new code keeps only `is_callable()`, so that guard is gone.
  - When `$isProcessing` is true, the code calls `$callMethod($actionMethod)` with no existence check at all. A request such as `process=true&action=anything` invokes `anything_action` on the controller, which routes into Smarty's `__call` or produces a PHP `Error`.
  - Impact is limited because the `_action` suffix constrains the reachable surface and the controller whitelist limits which classes are reachable. Still, this is a fail-open path where the old code failed closed.
- **Severity:** Medium
- **Fix:** Validate `$action` with `/^[A-Za-z0-9_]+$/`. Restore `method_exists()` alongside `is_callable()`. Only call `$processMethod` or `$actionMethod` after an explicit `method_exists()` check, and throw `NotFoundHttpException` otherwise.

### 2. Unsanitized user input in exception messages
- **Location:** `dispatch()`, `NotFoundHttpException("Action '$action' does not exist on controller: $className")`
- **OWASP:** A03:2021 Injection (reflected XSS, if rendered unescaped), A09:2021 Logging and Monitoring (information exposure)
- **Problem:** The old code echoed a regex-sanitized action name. The new code puts the raw `$action` into an exception message. If the front controller renders exception messages as HTML without escaping, this is reflected XSS. Messages also reveal internal class names.
- **Severity:** Low (depends on how the front controller renders exceptions)
- **Fix:** Validate `$action` first (see item 1). Escape any value in messages that might be rendered as HTML, and keep internal class names out of user-facing output.

### 3. Access control covers only two controllers
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The ACL map defines entries only for `practice_settings` and `prescription`. Eight other whitelisted controllers (`document`, `hl7`, `insurance_company`, `pharmacy`, `x12_partner`, and others) pass through with no check at this layer. This matches the pre-existing behavior, but the routing is now centralized, so any missing per-controller check is easier to miss. Authorization is therefore delegated entirely to each controller's own code, which is not visible in this diff.
- **Severity:** Low (informational for this PR; verify each whitelisted controller enforces its own ACL)
- **Fix:** Default-deny: require an ACL entry for every whitelisted controller, or document that each controller must check ACL itself.

### 4. `process` flag can be set via GET
- **Location:** `dispatch()`, `if (isset($params['process']))` followed by `$_POST['process'] = "true"`
- **OWASP:** A01:2021 Broken Access Control (CSRF-style risk)
- **Problem:** A GET request with `process` set is promoted to a POST-style state-changing action. This is pre-existing, but the diff keeps it. Any state-changing `_action_process` reached this way is exposed to cross-site request forgery unless the controller validates a CSRF token.
- **Severity:** Low (pre-existing; verify CSRF token validation in the `_process` methods)
- **Fix:** Accept `process` only on POST, and verify the CSRF token inside `_process` handlers.

### 5. Positional argument binding and type errors
- **Location:** `dispatch()`, `$callMethod(...array_values($args))`
- **OWASP:** A04:2021 Insecure Design
- **Problem:** Arguments are spread positionally in the order they appear in the query string, which the client controls. Array-valued parameters (e.g., `x[]=1`) are passed through unchanged and can trigger TypeErrors (HTTP 500) in typed action methods. Parameter values are not validated before reaching controller code.
- **Severity:** Low
- **Fix:** Bind arguments by name using reflection, or pass them as a single validated array. Reject array values where scalars are expected.

### 6. Logic error in `act()` breaks the `action` sub-action path
- **Location:** `act()`, the loop condition `if ($key === $controller || $key === $positionalAction) continue;`
- **OWASP:** Not a direct security flaw (A04:2021 Insecure Design, functional regression)
- **Problem:** For a legacy URL such as `?practice_settings&action=list`, `$positionalAction` is `'action'`. The loop then skips the `action` key, so `sub_action` is never set. The comment says this path should work. The call fails closed (the action method is not found), but the sub-controller delegation pattern breaks.
- **Severity:** Informational (functional bug, fails closed)
- **Fix:** Only skip the positional keys by position (index 0 and 1), not by name.

### 7. No audit logging of access denials or dispatch failures
- **Location:** `dispatch()` and `checkControllerAcl()`
- **OWASP:** A09:2021 Security Logging and Monitoring Failures
- **Problem:** Invalid controller names, missing actions, and ACL denials are thrown or rendered without an audit trail in this code. Probing of the routing layer would go unnoticed.
- **Severity:** Low
- **Fix:** Log rejected dispatches (controller, action, user ID, IP) through the existing audit logger.

---

### Checked and found acceptable
- **Injection (SQL/command):** None in this diff.
- **File inclusion:** The old code built the path from sanitized user input. The new code builds it from the whitelist value, so path traversal is no longer possible through `controller`.
- **Class instantiation:** `new $className()` only runs on whitelisted names.
- **SSRF / cryptography / deserialization:** Not applicable to this diff.

### Recommended priority
1. Restore `method_exists()`, validate `$action`, and remove the unchecked call path (items 1 and 2).
2. Confirm every whitelisted controller enforces ACL and CSRF on process actions (items 3 and 4).
3. Address argument typing, the `act()` bug, and logging (items 5 to 7).