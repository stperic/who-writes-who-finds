## Security Review: `Controller.class.php` (ACL map, `act()`→`dispatch()` refactor)

**Summary:** The change is a net hardening. The old `act()` built a class name from the URL and loaded any `C_*.class.php` file. The new code routes only through a whitelist (`VALID_CONTROLLERS`), so arbitrary controller loading is gone. I found no critical or high-severity issues. There are several medium and low issues, mostly in how the action name, the `process` flag, and error messages are handled.

---

### 1. State-changing actions reachable via GET without CSRF protection
- **Location:** `dispatch()`, the `isset($params['process'])` block, and the `$isProcessing` check.
- **OWASP:** A01 Broken Access Control (CSRF), A04 Insecure Design.
- **Problem:** Any request carrying a `process` parameter, including a GET request from a cross-site link or image, is converted into `$_POST['process'] = "true"` and runs `*_action_process`. This is the write path. Nothing in the diff checks a CSRF token or requires POST. The old code had the same behavior (`isset($_GET['process'])`), but `dispatch()` is now the documented entry point, so the weakness is more visible. Whether controllers check CSRF tokens themselves cannot be determined from this diff.
- **Severity:** Medium (higher if the process handlers perform writes without their own CSRF checks).
- **Recommendation:** Accept `process` only on POST, or require a CSRF token for all `_process` paths. Do not mutate `$_POST` from GET input.

### 2. Unsanitized user input in exception messages (possible reflected XSS)
- **Location:** `dispatch()`, `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
- **OWASP:** A03 Injection (XSS).
- **Problem:** The old code stripped `$c_action` to `[A-Za-z0-9_]` before using it. The new code passes the raw `action` parameter into the exception message. If the global exception handler renders messages without escaping (`controller.php` is not in the diff), an attacker can inject markup via a crafted URL.
- **Severity:** Medium (depends on the exception handler; not verifiable here).
- **Recommendation:** Do not echo raw user input in exception messages, or HTML-escape it at render time. Confirm how `controller.php` renders uncaught `HttpException`s. The same applies to the message for the `process` flow.

### 3. Dynamic method invocation without `method_exists()`
- **Location:** `dispatch()`, `$actionMethod = "{$action}_action"`, `is_callable([$controllerObj, $actionMethod])`, and `$callMethod`.
- **OWASP:** A03 Injection (method injection), A04 Insecure Design.
- **Problem:** `$action` comes unvalidated from the request and is turned into a method name. The removed code used both `is_callable()` and `method_exists()`, and its comment explains why: `Controller extends Smarty`, and Smarty's `__call` makes `is_callable()` return true for arbitrary names. The new code drops `method_exists()`, so any `<anything>_action` name can reach Smarty's magic `__call` with attacker-chosen names. Impact is probably limited because the target is restricted to `*_action` names on whitelisted classes, but this is a regression of a known pitfall.
- **Severity:** Low–Medium (needs verification against the Smarty version in use).
- **Recommendation:** Restore `method_exists()`, and validate `$action` against `/^[A-Za-z0-9_]+$/` as the old code did. Consider a per-controller explicit action allowlist.

### 4. Authorization for most controllers is implicit and not visible in this diff
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`.
- **OWASP:** A01 Broken Access Control.
- **Problem:** Only `practice_settings` and `prescription` are enforced at the dispatch layer. The other eight whitelisted controllers (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) depend entirely on their own constructors or action methods, which are not shown. Access to these controllers is now funnelled through one generic entry point, so a missing check in any of them is directly exposed. The old code had the same gap, so this is not a regression, but the whitelist makes it easier to see the gap and to miss it when adding controllers.
- **Severity:** Low–Medium (requires checking each controller).
- **Recommendation:** Verify each whitelisted controller's constructor or action enforces ACL, or add a required ACL entry for every whitelist item. Consider a default-deny policy. For example, `hl7` (HL7 message viewer) likely holds sensitive PHI and should be reviewed first.

### 5. Unvalidated request values passed directly to action methods
- **Location:** `dispatch()`, the `$args` build and `$callMethod(...array_values($args))`.
- **OWASP:** A03 Injection / A04 Insecure Design.
- **Problem:** All non-reserved query parameters are passed positionally to action methods with no type or content validation. Arrays (`?x[]=...`) are passed through, so actions can receive unexpected types, which may cause `TypeError` (500) responses. Safety depends on every action validating its inputs. The old code had the same property, but it had a `preg_replace` on argument names only, not values. Also, `$value === ''` only converts empty strings; the old `empty()` logic also turned `[]`/`null` into null, so behavior changed slightly.
- **Severity:** Low.
- **Recommendation:** Reject array values unless an action explicitly expects them. Use typed parameters in actions.

### 6. Minor information disclosure via error messages
- **Location:** `dispatch()`, the `BadRequestHttpException` and `NotFoundHttpException` messages, including `$className` and `$action`.
- **OWASP:** A05 Security Misconfiguration.
- **Problem:** Internal class names and action names are exposed in error messages. This is minor, and it becomes more significant if debug mode is on in production.
- **Severity:** Low.

---

### Positive observations
- The controller whitelist (`VALID_CONTROLLERS`) replaces arbitrary file and class loading from a sanitized URL segment, which is a meaningful security improvement.
- The file path is built only from whitelisted values, so there is no path traversal through `controller`.
- `FORM_ACTION` in `C_PracticeSettings` uses `attr()` on `$_SERVER['QUERY_STRING']`, which is correct. That file is unchanged, and no issue was found in it.

### Recommended before merge
1. Restore `method_exists()` and validate the `action` name (Issues 2 and 3).
2. Confirm that exception messages are escaped when rendered, or remove user input from them (Issue 2).
3. Restrict `process` handling to POST or enforce CSRF tokens (Issue 1).
4. Audit ACL enforcement in the eight whitelisted controllers that are not in `CONTROLLER_ACL_MAP` (Issue 4).