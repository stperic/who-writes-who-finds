## Security review: `Controller.class.php` routing refactor

**Summary:** I found no high-severity or directly exploitable injection flaw in this diff. The change removes the old regex-based name sanitization and replaces it with a whitelist for the controller name, which is a net improvement. The main concerns are authorization that now depends on code I cannot see, unvalidated method-name construction from user input, and GET-triggerable state changes. Severities below are my estimates from the diff alone.

### Findings

**1. Broken Access Control: ACL is enforced per-controller, and most controllers have no dispatch-level check (Medium, needs verification)**
- Location: `Controller::dispatch()` → `checkControllerAcl()`, and `CONTROLLER_ACL_MAP`
- Category: A01 Broken Access Control
- Problem: Only `practice_settings` and `prescription` have a dispatch-level ACL. `document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `pharmacy`, `patient_finder`, `x12_partner` and any future entry in `VALID_CONTROLLERS` are authorized only if their own constructors check ACL. The whitelist is therefore allow-by-default for ACL. Adding a controller to `VALID_CONTROLLERS` without also adding a `CONTROLLER_ACL_MAP` entry silently exposes it to any authenticated user if its constructor lacks a check. The `C_*` classes were not included in the diff, so I could not confirm that each has one. The old code had the same gap, but this change centralizes the routing and makes the gap easier to miss.
- Recommendation: Make the ACL map required for every whitelisted controller (deny-by-default), or require each controller to declare its ACL through `ControllerInterface`, and verify that every `C_*` constructor enforces its ACL.

**2. Injection / Unsafe Dynamic Dispatch: user-controlled action name builds a method name with no validation (Low–Medium)**
- Location: `dispatch()`: `$action = ... $params['action']`, `$actionMethod = "{$action}_action"`, `$callMethod(...)`
- Category: A03 Injection (dynamic method invocation), A04 Insecure Design
- Problem: The old code stripped non-`[A-Za-z0-9_]` characters from the action. The new code does not. Any string from `action` reaches `$controllerObj->$method(...)`. Two consequences:
  - When `$isProcessing` is true, the action method is called without `is_callable`/`method_exists` checks. An unknown action therefore triggers a PHP `Error` (or Smarty's `__call` if one is reachable) rather than the intended `NotFoundHttpException`. This can leak internals and bypasses the "does not exist" guard.
  - The `_action` suffix limits what can be reached, so I do not see a direct path to arbitrary public methods such as `dispatch` or `act`. Still, the defense now rests entirely on the suffix and on the callable check.
- Recommendation: Validate `$action` with `/^[A-Za-z][A-Za-z0-9_]*$/` and check `method_exists()` before calling on both branches.

**3. Authorization/CSRF: the `process` flag can be set from GET, so state-changing actions run on GET requests (Medium, pre-existing but touched)**
- Location: `dispatch()`: `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`
- Category: A01 Broken Access Control, A04 Insecure Design (CSRF)
- Problem: A `process` parameter in the query string makes the framework treat the request as a form submission, invoking `*_action_process`. A third-party page can trigger this with a single link or image tag. The framework adds no CSRF token check at this layer. Whether a given process handler is exploitable depends on its own token checks, which I could not see.
- Recommendation: Require POST for `process` handling and verify a CSRF token centrally before invoking any `*_process` method.

**4. Information Disclosure: internal class names and action names in exception messages (Low)**
- Location: `NotFoundHttpException("Unable to load controller: $className")`, `NotFoundHttpException("Action '$action' does not exist on controller: $className")`, `BadRequestHttpException`
- Category: A05 Security Misconfiguration, A09 Logging/Monitoring
- Problem: These messages reveal internal class names and file layout to the caller. Whether they reach the user depends on the global exception handler, which is not in the diff. If uncaught exceptions render with debug output, stack traces could also leak. The old code echoed a similar message, so this is a change in mechanism rather than a new leak.
- Recommendation: Return generic 400/404 responses to clients, and log the detailed message server-side.

**5. Parameter override / confusing routing precedence in `act()` (Low)**
- Location: `act()`: `$params = ['controller' => $controller, ...]` followed by the loop that writes `$params[$key]`
- Category: A04 Insecure Design
- Problem: A query key named `controller` (or `action`, handled via `sub_action`) is not excluded from the copy loop, so it can overwrite the positional controller. Example: `controller.php?practice_settings&controller=prescription`. The ACL check still runs against the effective controller, so this does not bypass ACL. It does make routing ambiguous and hard to audit.
- Recommendation: Skip the `controller` key in the copy loop, or reject requests that set it both positionally and by name.

**6. Robustness: array-valued parameters reach typed action arguments (Low)**
- Location: `dispatch()`: `$args[$key] = $value === '' ? null : $value;`
- Category: A03/A04 (input handling)
- Problem: Values are not type-checked before being spread into action methods, so `?x[]=1` yields an array passed to a `string`-typed parameter. This produces a `TypeError`, which can leak a stack trace if errors are displayed, and it reaches handlers that may not expect arrays.
- Recommendation: Reject or flatten non-scalar values before dispatch.

### Items to verify outside this diff
- Every `C_*` class in `VALID_CONTROLLERS` enforces its own ACL in its constructor or actions (see finding 1).
- The global exception handler does not render stack traces in production (see finding 4).
- `OEGlobalsBag::getString()` exists and behaves as expected. If it does not, this is a runtime error, not a security issue.
- `C_PracticeSettings` (shown above) passes `func_get_args()` through to `dispatch()`. The positional values cannot inject `controller` or `action` keys, because they are integer-keyed and `array_merge` only overwrites string keys, so this is safe as written.