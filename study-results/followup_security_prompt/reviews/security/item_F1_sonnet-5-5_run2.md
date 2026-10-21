## Security review: `Controller.class.php` routing refactor

Overall this is a net security improvement, but the diff introduces some regressions. I found no critical issues.

### Improvements
- The `VALID_CONTROLLERS` allow-list replaces the regex-sanitized name that was used to build an `include_once` path and a `new $obj_name()` call.
- The ACL check now uses the exact allow-listed controller key. The old check compared the raw first array key, so a case variant such as `Practice_Settings` could skip the check yet still resolve to `C_PracticeSettings` on a case-insensitive filesystem. That bypass is closed.
- Exceptions replace `echo ...; exit`.

### Findings

**1. Action name is no longer sanitized and is reflected in an exception message**
- **Location:** `dispatch()`, the `$action` assignment and `throw new NotFoundHttpException("Action '$action' does not exist ...")`
- **OWASP:** A03 Injection (reflected XSS), A04 Insecure Design
- **Problem:** The old code stripped everything outside `[A-Za-z0-9_]` from the action. The new code uses the raw `$params['action']` string. It is interpolated into the method name, `_current_action`, and the exception message. If the application's error handler renders exception messages as HTML without escaping, `?action=<script>…` becomes reflected XSS. Odd values such as `parent::x` can also reach `is_callable()`, which accepts class-qualified callables.
- **Fix:** Restore the `preg_match('/^[A-Za-z0-9_]+$/', $action)` validation and throw `BadRequestHttpException` with a static message. Do not echo user input.
- **Severity:** Low to Medium, depending on how the error handler renders messages.

**2. `method_exists()` guard dropped, so Smarty's `__call` makes `is_callable()` always true**
- **Location:** `dispatch()`, `is_callable([$controllerObj, $actionMethod])` and the `$isProcessing || ...` branch
- **OWASP:** A04 Insecure Design, A05 Security Misconfiguration
- **Problem:** The removed code carried a comment explaining that Smarty 4's `__call` makes `is_callable()` always true, so it also checked `method_exists()`. The new code checks only `is_callable()`. Consequences:
  - The "action does not exist" branch is effectively dead.
  - Any `*_action` name is forwarded into Smarty's magic `__call`.
  - In processing mode, the action is called with no existence check at all.
  - Missing methods surface as uncaught `Error` or `SmartyException`, which can leak internals or cause a 500.
- **Fix:** Require `method_exists($controllerObj, $method) && is_callable(...)`, and add an explicit allow-list or naming check.
- **Severity:** Medium.

**3. Positional argument binding from arbitrary request parameters**
- **Location:** `dispatch()`, the `$args` build and `...array_values($args)`; `act()`, the `sub_action` renaming
- **OWASP:** A04 Insecure Design
- **Problem:** The docs advertise "order-independent routing", but every non-reserved query parameter is still passed positionally in URL order. The array keys are discarded by `array_values`. An attacker can reorder or inject parameters, for example `?controller=document&action=view&doc_id=1&patient_id=2`, so that values land in different method parameters than intended. Values can also be arrays (`foo[]=x`), because there is no type check. This can defeat patient-scoped checks inside controllers. In `act()`, the `sub_action` rename also injects an extra positional argument, which shifts the legacy callers' arguments.
- **Fix:** Bind by name using reflection, spreading string keys as named arguments after filtering to the method's declared parameters. Cast or validate types.
- **Severity:** Medium. The legacy code had the same weakness, but the refactor presents it as fixed.

**4. State-changing "process" triggered via GET (pre-existing, carried forward)**
- **Location:** `dispatch()`, the `isset($params['process'])` block that sets `$_POST['process'] = "true"`
- **OWASP:** A01 Broken Access Control (CSRF), A04 Insecure Design
- **Problem:** A GET parameter is promoted to a POST flag, so `*_action_process` handlers run from a plain link, such as an image tag or a redirect. Nothing in this diff verifies a CSRF token.
- **Fix:** Require `REQUEST_METHOD === 'POST'` and verify a CSRF token before running process handlers.
- **Severity:** Medium. Pre-existing, but worth fixing while this code is being rewritten.

**5. ACL coverage is limited to two controllers (informational)**
- **Location:** `CONTROLLER_ACL_MAP`
- **OWASP:** A01 Broken Access Control
- **Problem:** `document`, `insurance_company`, `pharmacy`, `x12_partner`, `hl7`, `patient_finder` and others have no central ACL check. This matches the old behavior, but a default-deny design is safer. Confirm that each of these controllers enforces its own ACL checks.
- **Severity:** Low (informational).

### Minor
- `act()` reads `$keys[0]` without checking for an empty array, which gives a PHP warning and an empty controller name. The result is a 400, which is safe.
- Exception messages disclose internal class names. Keep them generic in production.

### Recommendation
Fix #1 and #2 before merging, since both are straightforward regressions from the old code. Track #3 and #4 as follow-ups.