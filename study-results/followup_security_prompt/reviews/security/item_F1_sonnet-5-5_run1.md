## Security review: `Controller::act()` / `dispatch()` refactor

No critical or high-severity issues are introduced. The change fixes real problems in the old code, but it also adds a few regressions and leaves some older weaknesses in place.

### Improvements
- **Controller whitelist (`VALID_CONTROLLERS`).** This replaces building a filename from user input and then `include_once`-ing it, so arbitrary controller loading is no longer possible.
- **ACL bypass fixed.** The old code compared the raw first key to `'practice_settings'` and `'prescription'`, but then derived the class name with `ucfirst` per segment. A request like `?Practice_settings&...` skipped the ACL check and still loaded `C_PracticeSettings`. Now the ACL check and the class lookup both use the same whitelisted value.
- **Safer failure handling.** Errors are thrown as HTTP exceptions instead of `echo` followed by `exit`.

### Findings

**1. Unsanitized `action` reflected in exception message**
- **Location:** `dispatch()`, `throw new NotFoundHttpException("Action '$action' does not exist ...")`
- **OWASP:** A03 Injection (XSS), A05 Misconfiguration
- **Problem:** The old code stripped the action with `preg_replace('/[^A-Za-z0-9_]/', '')`. That sanitization was removed, so `$action` is now raw user input placed into an exception message. If the error handler renders the message as HTML without escaping, this is reflected XSS. Other unsanitized input in the exception path is also at risk.
- **Severity:** Low to Medium, depending on how exceptions are rendered.
- **Fix:** Restrict the action with `preg_match('/^[A-Za-z0-9_]+$/')` before use, and don't echo user input in messages.

**2. Weaker action-existence check; arbitrary `*_action` method invocation**
- **Location:** `dispatch()`, `is_callable([$controllerObj, $actionMethod])` and the `$isProcessing ||` branch
- **OWASP:** A04 Insecure Design
- **Problem:**
  - The removed code carried a comment that `is_callable()` is always true on Smarty 4 because of `__call`, so `method_exists()` is also needed. The new code drops `method_exists()`. The "does not exist" branch is therefore effectively dead, and unknown actions fall into Smarty's `__call` handling.
  - When `process=true`, the action method is invoked unconditionally.
  - Any public `*_action` method on a whitelisted controller is reachable, because `is_callable` is evaluated in `Controller` scope and so may also include protected methods.
- **Severity:** Low.
- **Fix:** Restore `method_exists()`, validate the action name format, and ideally keep an explicit per-controller allowlist of actions.

**3. Arguments are passed positionally in attacker-controlled order**
- **Location:** `dispatch()`, `$controllerObj->$method(...array_values($args))`
- **OWASP:** A01 Broken Access Control, A04 Insecure Design
- **Problem:**
  - The docblock claims "order-independent routing", but remaining params are spread by position in query-string order, with names discarded.
  - A request with `doc_id=…&patient_id=…` reversed binds the values to the wrong parameters. This can cause parameter confusion, for example swapping patient and document IDs. It could defeat per-patient authorization checks or produce IDOR-like behavior.
  - Extra or array-valued params (`x[]=`) can also trigger `TypeError`s (500s).
- **Severity:** Medium (design flaw).
- **Fix:** Bind by name using reflection and named arguments, reject unknown params, and validate types.

**4. Loose-to-strict comparison on `_state` (possible fail-open)**
- **Location:** `if ($controllerObj->_state === false)`
- **OWASP:** A04 Insecure Design
- **Problem:** The original used `== false`. A process action that signals "stop" with `0`, `null` or `''` no longer halts, so the follow-on action (rendering or another operation) runs when it previously wouldn't.
- **Severity:** Low. Audit the controllers that set `_state`.

**5. Parameter pollution in `act()`**
- **Location:** `act()`, the `$params[$key] = $value` loop
- **OWASP:** A04
- **Problem:** Only `action` is renamed. A legacy URL containing an extra `controller=` key overwrites `$params['controller']`. Because the ACL check runs on the final value, this is not an ACL bypass, but it makes routing confusing. Rename or skip all reserved keys.
- **Severity:** Informational.

**6. Pre-existing weaknesses that remain (not introduced by this diff)**
- **ACL coverage (A01).** Only `practice_settings` and `prescription` have ACL entries. `hl7`, `x12_partner`, `insurance_company`, `insurance_numbers`, `pharmacy`, `document_category`, `patient_finder` and `document` are enforced only if each action checks for itself. Adding a deny-by-default ACL for every whitelisted controller would be much safer. Severity: Medium if per-action checks are missing.
- **CSRF (A01/A04).** Passing `process` in the query string (GET) sets `$_POST['process']='true'`, so state-changing "process" actions can be triggered by a GET request. There is no CSRF token validation in the dispatcher. Severity: Medium.

### Summary

| # | Issue | Severity |
|---|-------|----------|
| 1 | Unsanitized action in exception message (XSS risk) | Low–Med |
| 2 | Dropped `method_exists` / action validation | Low |
| 3 | Positional argument binding in attacker-controlled order | Medium |
| 4 | `_state` strict comparison fail-open | Low |
| 5 | Reserved-param override in `act()` | Info |
| 6 | Pre-existing: missing ACLs on most controllers, GET-triggered process, no CSRF | Medium |

I recommend addressing #1–#3 before merging. #6 is best handled as a follow-up.