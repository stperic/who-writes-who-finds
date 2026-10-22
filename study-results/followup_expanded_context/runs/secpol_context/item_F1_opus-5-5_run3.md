# Security Review: `library/classes/Controller.class.php` routing refactor

**Summary:** The new controller whitelist is an improvement. However, the refactor removes two protections from the old code: it no longer sanitizes the action name, and it drops the `method_exists()` guard that the old code's own comment said was required because of Smarty 4. It also keeps several older access-control and CSRF weaknesses.

---

### 1. The action name is no longer sanitized and the `method_exists()` guard was removed
- **Location:** `dispatch()`, where `$action`, `$actionMethod` and `$processMethod` are built, and the `is_callable` / `$isProcessing` branches.
- **OWASP category:** A03 Injection / A04 Insecure Design.
- **Problem:**
  - The old code removed any character outside `[A-Za-z0-9_]` from the action name. It also required both `is_callable()` and `method_exists()`, because Smarty 4's `__call` makes `is_callable()` return true for any method name.
  - The new code uses the raw `$params['action']` value and checks only `is_callable()`. That check always passes on a Smarty subclass.
  - When `$isProcessing` is true, `$actionMethod` is called with no check at all. Note that processing mode can be switched on through `?process=` in the URL.
  - Result: any attacker-chosen string ending in `_action` is handed to Smarty's magic `__call` and extension dispatcher (`_callExternalMethod`). That code does name-pattern-based method and property dispatch and was never meant to receive attacker input.
  - The "does not exist" branch is now effectively unreachable. Unknown actions go into Smarty internals instead of producing a clean 404.
  - The same applies to the nested `dispatch()` calls in `C_PracticeSettings::*_action($arg)`. There, `$arg` (the sub-action) comes straight from the request.
- **Fix:**
  1. Validate the action with `preg_match('/^[A-Za-z0-9_]+$/', $action)`.
  2. Restore `method_exists($controllerObj, $method)` for both the process method and the action method, including on the processing path.
  3. Better still, use `ReflectionMethod` and require the method to be public and declared on a `C_*` class, not inherited from Smarty or `Controller`.
- **Severity:** High.

### 2. Unescaped request data in exception messages (possible reflected XSS or information disclosure)
- **Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className")`. A lower-risk instance is `"Unable to load controller: $className"`.
- **OWASP category:** A03 Injection (XSS) / A05 Security Misconfiguration.
- **Problem:**
  - `$action` is raw user input. It used to be limited to alphanumerics before it was echoed.
  - If the exception is rendered by an HTML error page, Symfony debug output, or PHP's uncaught-exception output with `display_errors` on, it becomes reflected XSS. For example: `controller.php?controller=document&action=<script>...`.
  - Note: because of issue #1 this path is rarely reached today. Fixing #1 alone, without escaping, would make it reachable.
- **Fix:** Do not reflect the input. Use a generic message, or escape it with `text()`/`attr()` when rendering, and make sure the error handler HTML-encodes messages.
- **Severity:** Medium.

### 3. ACL is enforced only for two top-level controllers (pre-existing, kept by this change)
- **Location:** `CONTROLLER_ACL_MAP` and `checkControllerAcl()`.
- **OWASP category:** A01 Broken Access Control.
- **Problem:**
  - Only `practice_settings` (admin/practice) and `prescription` (patients/rx) are checked.
  - In the UI, `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, `hl7`, `document` and `document_category` are reached through Practice Settings, which requires admin/practice.
  - They are also in `VALID_CONTROLLERS`, so they can be called directly. For example, `controller.php?controller=x12_partner&action=edit` reaches them without any admin/practice check.
  - Unless every `C_*` class performs its own ACL check in its constructor or actions (only `C_PracticeSettings` visibly does), this is a direct authorization bypass. It exposes billing partner configuration, insurance data, HL7 data, and patient documents. Document access should also be tied to the patient (patients/docs ACL plus patient context).
- **Fix:**
  - Add an ACL entry for every whitelisted controller and deny by default when a controller has no entry.
  - Keep per-action checks inside the controllers for defense in depth.
- **Severity:** High.

### 4. State-changing "process" handlers can be triggered by GET, with no CSRF check in the dispatcher (pre-existing)
- **Location:** `if (isset($params['process'])) { ... $_POST['process'] = "true"; }` and `$isProcessing`.
- **OWASP category:** A01 Broken Access Control (CSRF) / A04 Insecure Design.
- **Problem:**
  - Any GET request containing `process` turns on processing mode and calls `*_action_process` handlers. These write to the database (practice settings, pharmacies, insurance companies, X12 partners, documents).
  - A link or image tag can therefore cause state changes in an authenticated session.
  - The dispatcher performs no CSRF token check, so protection depends entirely on each handler.
- **Fix:**
  - Require `$_SERVER['REQUEST_METHOD'] === 'POST'` for processing.
  - Verify the CSRF token centrally (`CsrfUtils::verifyCsrfToken`) before calling any `_process` method.
  - Stop converting GET `process` into `$_POST['process']`.
- **Severity:** Medium–High.

### 5. Arbitrary positional arguments are passed to action methods (pre-existing, weakened slightly)
- **Location:** `$callMethod` → `$controllerObj->$method(...array_values($args))`.
- **OWASP category:** A04 Insecure Design.
- **Problem:**
  - Every leftover query parameter becomes a positional argument, in whatever order the attacker supplies.
  - The values are no longer type-checked and can be arrays, for example `foo[]=x`. Action methods that assume scalar arguments may misbehave or produce errors.
  - Combined with #1, the attacker controls both which method is called and its arguments.
- **Fix:**
  - Map parameters to method arguments by name using reflection.
  - Reject non-scalar values unless an argument explicitly expects them.
- **Severity:** Low–Medium.

---

### Positive notes
- The `VALID_CONTROLLERS` whitelist removes the earlier risk of arbitrary file includes or class instantiation through the controller name.
- The ACL check now runs before the controller is instantiated.

### Merge recommendation
Block the merge until #1 and #2 are fixed, since both are regressions introduced by this PR. Track #3 and #4 as high-priority follow-ups, ideally fixed in this same refactor because it centralizes routing.