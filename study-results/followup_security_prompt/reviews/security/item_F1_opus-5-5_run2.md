# Security Review: `library/classes/Controller.class.php`

## Summary

The new allow-list for controller names is a real improvement. The old code built an `include_once` path from user input. However, the refactor removes the input sanitization on the action name and drops the `method_exists()` guard. The old code's comments explained that this guard is required under Smarty 4. Several weaknesses that already existed are also kept.

---

## Findings

### 1. Action name no longer sanitized; `method_exists()` guard removed
- **Location:** `dispatch()`. See `$action = is_string($params['action'] ?? null) ? ...`, `is_callable([$controllerObj, $actionMethod])`, and `$callMethod`.
- **OWASP:** A03 Injection / A04 Insecure Design
- **Problem:**
  - The old code removed every character except `[A-Za-z0-9_]` from the action name. The new code uses the raw `action` value to build the method name `"{$action}_action"` and the `_process` variant.
  - The removed comment explained the risk. Smarty 4 defines `__call`, so `is_callable()` always returns true. The old code therefore also required `method_exists()`. The new code only checks `is_callable()`.
  - As a result, any `action` value passes the check. The call goes to Smarty's `__call` / extension handler (`Smarty_Internal_Extension_Handler`) instead of failing safely. That handler resolves method names dynamically, including `set*`/`get*` property accessors and loading `Smarty_Internal_Method_*` classes. Attacker-chosen method names now reach Smarty's internal dispatch, together with attacker-supplied positional arguments.
  - The "action does not exist" 404 branch can no longer be reached for real controllers.
  - The impact depends on the Smarty version. Even so, this weakens a deliberate control and widens the reachable attack surface.
- **Fix:**
  - Validate the action against `/^[A-Za-z0-9_]+$/` and reject anything else. Do not silently strip characters.
  - Restore `method_exists($controllerObj, $method)` for both `$processMethod` and `$actionMethod`, alongside or instead of `is_callable()`.
  - Only call the `_action` method when `$isProcessing` is true if `method_exists()` confirms it exists.
- **Severity:** **High.** This is a regression of an explicit safety check.

### 2. Unsanitized action stored and reflected (possible XSS)
- **Location:**
  - `$controllerObj->_current_action = $action;`
  - `throw new NotFoundHttpException("Action '$action' does not exist ...")`
- **OWASP:** A03 Injection (XSS)
- **Problem:**
  - `_current_action` is used by `_link()` and templates to build URLs and markup. It was previously guaranteed to be alphanumeric. It can now contain quotes, `<`, `>`, `&`, CRLF, and similar characters. Any template or link that outputs it without escaping becomes a reflected XSS vector.
  - Exception messages that include user input are also reflected wherever the exception handler renders them, for example in debug pages or error templates.
- **Fix:**
  - Validate the action strictly, as in Finding 1, before storing or echoing it.
  - Escape it on output.
  - Keep raw user input out of exception messages, or make sure the handler never renders them unescaped.
- **Severity:** **Medium.**

### 3. Sub-controllers reachable directly, bypassing parent ACL (pre-existing, now codified)
- **Location:** `VALID_CONTROLLERS` / `CONTROLLER_ACL_MAP`
- **OWASP:** A01 Broken Access Control
- **Problem:**
  - Only `practice_settings` (`admin/practice`) and `prescription` (`patients/rx`) have ACL checks.
  - `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, `document_category`, and `hl7` are normally administered through Practice Settings. The allow-list lets anyone call them directly with no ACL at the router level. For example, `controller=pharmacy&action=edit` skips the `admin/practice` check entirely.
  - This existed before the change. The new explicit allow-list is the natural place to fix it, and leaving those entries out of `CONTROLLER_ACL_MAP` makes the gap official.
- **Fix:** Add ACL entries for every allowed controller. Default-deny any controller that has no ACL entry.
- **Severity:** **High.** These controllers can modify billing and insurance data, though the gap is pre-existing.

### 4. `process` flag via GET enables state change without POST/CSRF protection (pre-existing)
- **Location:** `if (isset($params['process'])) { ... $_POST['process'] = "true"; }`
- **OWASP:** A01 Broken Access Control (CSRF) / A04 Insecure Design
- **Problem:**
  - A GET parameter is turned into a POST "process" request, which runs `*_action_process` handlers that change state.
  - A link or image tag can therefore trigger writes, such as saving pharmacy or insurance records, for a logged-in user.
  - No CSRF token check appears in this dispatch path.
- **Fix:**
  - Require a real POST request for processing.
  - Verify the CSRF token (for example `CsrfUtils::verifyCsrfToken`) before calling any `_process` method.
- **Severity:** **Medium.** This is pre-existing and preserved by the refactor.

---

## Positive Changes
- The controller allow-list removes the user-controlled file-include path (previously only stripped by regex). This is a meaningful reduction in LFI and class-instantiation risk.
- The ACL is evaluated on the final resolved controller name. A later `controller=` parameter overriding the positional one in `act()` therefore cannot bypass the ACL.
- Throwing proper HTTP exceptions replaces `echo`/`exit` paths that echoed unescaped input.

## Recommendation
**Request changes.**
- Fix Findings 1 and 2 before merging, since they are regressions introduced by this PR.
- Address Findings 3 and 4 in this PR or in a tracked follow-up, since the new routing layer is the right place to enforce both.