# Security Review: `Controller::act()` / `Controller::dispatch()` refactor

The controller whitelist is a real improvement. The old code built a file path from user input, and the whitelist removes that path-injection risk on the controller side. However, the refactor drops two safeguards the old action-handling code had. It also leaves several existing access-control and CSRF weaknesses in place.

---

## 1. Unsanitized action name sent to dynamic method dispatch and Smarty's magic `__call`
**Location:** `Controller::dispatch()`, where `$action`, `$actionMethod`, `$processMethod`, `is_callable(...)` and `$callMethod(...)` are built and used
**OWASP:** A03 Injection, and A04 Insecure Design
**Severity:** High (regression introduced by this PR)

**What changed:**
- The old code stripped everything except `[A-Za-z0-9_]` from the action before using it. The new code uses `$params['action']`, which comes straight from `$_GET`, with no sanitizing:
  ```php
  $action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
  $actionMethod = "{$action}_action";
  ```
- The old code also had a comment warning that, under Smarty 4, `is_callable()` is always true. Smarty implements `__call`, which accepts any method name. For that reason the old code required both `is_callable()` and `method_exists()`. The new code removes the `method_exists()` check.

**Consequences:**
- **The not-found branch is effectively unreachable.** `is_callable([$controllerObj, $actionMethod])` is always true, so `NotFoundHttpException` is never thrown.
- **Any action string is accepted.** Every attacker-chosen string is called as `$controllerObj->{"<input>_action"}(...)`.
- **The input reaches Smarty's extension loader.** Names that are not real methods fall into Smarty's `__call` → `_callExternalMethod()`. That code builds a class name (`Smarty_Internal_Method_<Name>`) and triggers Smarty's autoloader, which turns the class name into a file path under the sysplugins directory.
- **Path traversal becomes possible.** Without the old character filter, input containing `/`, `.`, `\` or null bytes reaches that file lookup. This creates a path-traversal and file-inclusion risk, and at minimum an unpredictable attack surface.
- **The `process` path is worse.** With `process` set, `$isProcessing` is true and `$actionMethod` is called with no callable check at all:
  ```php
  if ($isProcessing || is_callable([$controllerObj, $actionMethod]))
  ```
- **The same problem occurs in sub-dispatches.** `C_PracticeSettings::*_action($arg)` passes the user-controlled `$arg` as the nested `action`.

**Fix:**
- Validate the action strictly, then confirm the method really exists:
  ```php
  if (!preg_match('/^[A-Za-z0-9_]+$/', $action)) { throw new BadRequestHttpException(...); }
  ...
  if ($isProcessing && method_exists($controllerObj, $processMethod)) { ... }
  if (method_exists($controllerObj, $actionMethod)) { ... } else { throw new NotFoundHttpException(...); }
  ```
- Better still, use reflection to confirm the method is public and declared on the controller class, not inherited from `Smarty`.

---

## 2. Raw user input placed in exception messages (reflected XSS and information disclosure)
**Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`
**OWASP:** A03 Injection (XSS)
**Severity:** Medium (regression introduced by this PR)

**Problem:**
- The old code only echoed the action after the regex sanitizing.
- The new message contains the raw `$action` value.
- If the exception is shown by an error handler or debug page that does not HTML-escape messages, this is reflected XSS in an authenticated EHR session.
- The message also reveals internal class names, and the same applies to the controller-load failure message.

Once finding #1 is fixed this branch becomes reachable, so the issue matters more after the fix.

**Fix:** Validate `$action` before using it (see #1). Keep user input out of exception messages, or make sure every rendering path escapes it.

---

## 3. Directly routable sub-controllers have no ACL enforcement
**Location:** `VALID_CONTROLLERS` and `CONTROLLER_ACL_MAP` in `Controller.class.php`; related to `C_PracticeSettings`
**OWASP:** A01 Broken Access Control
**Severity:** High, if the target controllers lack their own checks (existing issue, now formalized by this PR)

**Problem:**
- `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, `hl7`, `document_category` and `patient_finder` are administrative screens. They are meant to be reached through `practice_settings`, which enforces `admin/practice` in `C_PracticeSettings::__construct`.
- However, they are whitelisted as top-level controllers, and `CONTROLLER_ACL_MAP` covers only `practice_settings` and `prescription`.
- As a result, any authenticated user can bypass the `admin/practice` check by requesting the sub-controller directly:
  - `controller.php?pharmacy&edit&id=1&process=true`
  - `controller.php?controller=x12_partner&action=edit`
- That allows modifying pharmacies, insurance companies, X12 partners and similar records, and viewing HL7 data, without the practice-admin permission.
- The old code allowed this too. This PR now explicitly blesses these routes and leaves out their ACLs.

**Fix:**
- Add ACL entries for every whitelisted controller, for example `['admin','practice', ...]` for the practice-settings sub-controllers. Use the appropriate patient or document ACLs for `document` and `patient_finder`.
- Alternatively, require `ControllerInterface` implementations to declare their ACL, and deny by default when none is declared.

---

## 4. GET `process` parameter promoted to `$_POST['process']` (CSRF-prone design)
**Location:** `dispatch()`, the "Handle process flag" block
**OWASP:** A01 Broken Access Control (CSRF), and A04 Insecure Design
**Severity:** Medium (existing issue, carried forward)

**Problem:**
- A query-string `process` parameter sets `$_POST['process'] = "true"`. This runs the state-changing `*_action_process` methods.
- The router performs no CSRF token check. The individual controllers are not verified to perform one either.
- A cross-site link or image tag aimed at a logged-in user could therefore trigger writes. Combined with finding #3, this widens the impact.

**Fix:**
- Only treat a request as processing when it is an actual POST request.
- Have the dispatcher verify the CSRF token (`CsrfUtils::verifyCsrfToken`) before calling any `*_process` method.

---

## 5. Minor issues and observations

**`$_GET` mutated from `dispatch()` (Low, design):**
- `dispatch()` takes a `$params` array but still changes global `$_GET` and `$_POST`.
- Nested dispatches from `C_PracticeSettings` therefore share and alter global request state. This makes the processing decision hard to reason about.

**Array and non-scalar argument values (Low):**
- User-supplied values, including arrays such as `foo[]=...`, are passed positionally to action methods.
- Argument position depends on query-string order, so an attacker controls which value lands in which parameter.
- The old code had the same behavior. Consider typed or named parameter binding.

**`C_PracticeSettings` constructor (Informational):**
- It uses `attr($_SERVER['QUERY_STRING'])` for `FORM_ACTION`. This is escaped and acceptable.

---

### Summary

| # | Issue | OWASP | Severity | New/Existing |
|---|---|---|---|---|
| 1 | Unsanitized action name; `method_exists` removed, so Smarty `__call` and autoloader are reachable | A03/A04 | High | New |
| 2 | Raw action in exception message (XSS, info leak) | A03 | Medium | New |
| 3 | Sub-controllers routable without ACL (bypass of `admin/practice`) | A01 | High | Existing (formalized) |
| 4 | GET → `$_POST['process']` with no CSRF check | A01/A04 | Medium | Existing |
| 5 | Global state mutation, positional untyped args | A04 | Low | Existing |

**Recommendation:** Request changes. Restore the strict action validation and the `method_exists()` check before merging. Extend `CONTROLLER_ACL_MAP` so that every whitelisted controller has an ACL, denying by default when none is set.