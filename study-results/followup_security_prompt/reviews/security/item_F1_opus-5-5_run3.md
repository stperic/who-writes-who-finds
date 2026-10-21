# Security Review: `Controller.class.php` routing refactor

The controller whitelist is a real improvement. It replaces the old regex-and-`include` approach for picking the controller class. However, the **action** half of the routing lost its input sanitization and its method-existence check, and that opens a new attack surface.

---

### 1. Unsanitized action name plus removed `method_exists()` check enables arbitrary magic-method invocation

**Location:** `dispatch()`: the `$action` / `$actionMethod` / `$processMethod` construction and both `is_callable()` checks. Also `act()`, which passes `$keys[1]` straight through as the action.

**OWASP:** A03:2021 Injection, A01:2021 Broken Access Control, A04:2021 Insecure Design

**Problem:**
- **Sanitization removed.** The old code ran the action through `preg_replace("/[^A-Za-z0-9_]/", "", ...)`. The new code uses `$params['action']` verbatim, so any string (`../`, `:`, `\`, etc.) becomes part of the method name.
- **`method_exists()` guard removed.** The deleted comment explained why it existed: since Smarty 4, `Controller` (which `extends Smarty`) has a `__call()`, so `is_callable([$controllerObj, <anything>])` is **always true**. The new code relies only on `is_callable()`, so every action name passes the check.
- **The call reaches Smarty's `__call()`.** Any action that isn't a real method goes to `Smarty_Internal_Extension_Handler`, with an attacker-chosen name and attacker-chosen arguments (all remaining query params via `...array_values($args)`). That handler:
  - treats `get*`/`set*`-prefixed names as property accessors, letting an attacker try to read or write Smarty properties;
  - otherwise builds `Smarty_Internal_Method_<Name>` and calls `class_exists()`. That triggers Smarty's autoloader, which builds a file path from the class name and `include`s it if the file exists. With the action unsanitized, path characters reach that file-name construction. This is a plausible route to local file inclusion of `*_action.php` / `*_action_process.php` files, depending on the Smarty version and autoloader in use.
- **Safety net gone.** Even without a full exploit chain, the old safe failure ("action does not exist") is replaced by reaching deep, unintended framework code paths.

**Severity:** **High**

**Fix:**
- Restore strict validation, e.g. `if (!preg_match('/^[A-Za-z0-9_]+$/', $action)) throw new BadRequestHttpException(...)`.
- Restore `method_exists($controllerObj, $actionMethod)`, or better, use `ReflectionMethod` to confirm the method is public and declared on the controller class, not inherited from `Smarty`.
- Apply the same check to `$processMethod`.
- Don't call `$actionMethod` unconditionally when `$isProcessing` is true (see #2).

---

### 2. Action method is called unconditionally when `process=true`

**Location:** `if ($isProcessing || is_callable([$controllerObj, $actionMethod]))`

**OWASP:** A04:2021 Insecure Design

**Problem:** When processing, the action method is invoked with no existence check at all. This carries over from the old code's structure, but combined with #1 it guarantees that any attacker-supplied name is dispatched to `__call()`.

**Severity:** **Medium.** It amplifies #1 and is fixed by the same change.

---

### 3. GET request can trigger state-changing `*_action_process` handlers (CSRF exposure)

**Location:** The "Handle process flag" block in `dispatch()`.

**OWASP:** A01:2021 Broken Access Control (CSRF), A04:2021 Insecure Design

**Problem:** A `process` query parameter sets `$_POST['process'] = "true"`. This lets a plain GET link or `<img>` tag invoke write handlers such as `edit_action_process`. Any CSRF protection that keys on real POST bodies or the request method is bypassed.

This behavior existed before. The refactor now also honors `process` from any `$params` source, which widens it slightly. Since this code is being rewritten anyway, it is the right time to fix it.

**Severity:** **Medium** (largely pre-existing)

**Fix:**
- Only run `*_action_process` for genuine POST requests.
- Verify the CSRF token centrally in `dispatch()` before any process method is called.

---

### 4. Reflected, unsanitized input in exception messages

**Location:** `throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");`

**OWASP:** A03:2021 Injection (XSS), A05:2021 Security Misconfiguration

**Problem:** `$action` is now raw user input. If the exception message is rendered to the browser without HTML-escaping (debug error pages, custom handlers that echo `getMessage()`), this is reflected XSS. The old `echo` also reflected input, but only after it had been stripped to `[A-Za-z0-9_]`.

**Severity:** **Low–Medium** (depends on how exceptions are rendered)

**Fix:** Validate the action as in #1, and/or don't echo user input in exception messages. Make sure exception rendering escapes output.

---

### 5. Coarse, opt-in ACL coverage (pre-existing, not a regression)

**Location:** `CONTROLLER_ACL_MAP`

**OWASP:** A01:2021 Broken Access Control

**Problem:** Only `practice_settings` and `prescription` get a router-level ACL check. Controllers such as `pharmacy`, `insurance_company`, `x12_partner`, `hl7`, and `document` are reachable directly via `?controller=pharmacy` without the `admin/practice` check that applies when they are reached through `practice_settings`. They depend entirely on their own internal checks. This matches the prior behavior, but the new explicit `dispatch()` entry point makes direct addressing more obvious.

**Severity:** **Low** (informational / hardening)

**Fix:** Require every entry in `VALID_CONTROLLERS` to have an ACL entry, failing closed. Alternatively, explicitly audit each controller for internal ACL checks.

---

### Minor / informational

- **Arguments not validated.** All non-reserved query params, including arbitrary extra keys and array-valued params (`foo[]=`), are now passed positionally to action methods. Argument position is decided by query-string order, and types are unchecked. This isn't directly exploitable on its own, but it can cause type confusion in action methods. Consider mapping arguments by name with reflection and enforcing scalar types.
- **Improvement noted.** The controller whitelist (`VALID_CONTROLLERS`) removes the previous dynamic file-inclusion surface from the controller name. That part of the change is a security improvement.

---

### Summary

| # | Issue | OWASP | Severity |
|---|---|---|---|
| 1 | Unsanitized action and missing `method_exists()` reach Smarty `__call()` (possible property tampering / LFI) | A03, A01, A04 | **High** |
| 2 | Action method called unconditionally when processing | A04 | Medium |
| 3 | GET triggers `*_action_process` (CSRF) | A01, A04 | Medium (pre-existing) |
| 4 | Raw action reflected in exception message | A03, A05 | Low–Medium |
| 5 | Router ACL only covers 2 of 10 controllers | A01 | Low (pre-existing) |

**Recommendation:** Request changes. Issue #1 must be fixed before merging by restoring action-name validation and a real method-existence check that excludes inherited Smarty methods.