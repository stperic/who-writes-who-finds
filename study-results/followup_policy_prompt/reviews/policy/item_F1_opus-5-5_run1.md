## Code review: `Controller::act()` / `Controller::dispatch()` refactor

### 1. Action name is unsanitized and `method_exists()` was dropped (High: security and correctness)
**Location:** `dispatch()`: building `$actionMethod` / `$processMethod`, and both `is_callable()` checks.

**Problem:**
- The old code stripped the action with `preg_replace("/[^A-Za-z0-9_]/", "", …)`. The new code uses the raw `$params['action']` from `$_GET` as part of a method name.
- The old code also checked `method_exists()` alongside `is_callable()`. Its comment explained why: Smarty 4 defines `__call()`, so `is_callable()` is **always true** on a `Smarty` subclass. Both the comment and the check were removed.

**Consequences:**
- **Arbitrary method names reach Smarty's `__call()`.** Smarty routes them to `ext->_callExternalMethod()`, which runs get/set property magic and tries to autoload `Smarty_Internal_Method_<name>`. Attacker-controlled strings (`/`, `..`, null bytes, etc.) therefore flow into the Smarty and Composer autoloaders and into magic dispatch. This attack surface did not exist before.
- **Nonexistent actions no longer get a 404.** The `NotFoundHttpException` branch is effectively dead. Requests for missing actions hit `__call()` and throw a `SmartyException` instead.
- **Every POST with `process=true` breaks if the action has no `_process` method.** `is_callable([$obj, $processMethod])` is always true, so `__call()` throws instead of the request falling through to the normal action.

**Fix:**
- Validate the action, e.g. `preg_match('/^[A-Za-z0-9_]+$/', $action)`. Reject anything else with `BadRequestHttpException`.
- Restore `method_exists()` for both the process method and the action method.
- Consider additionally verifying the method is public and declared on the `C_*` class, not inherited from `Smarty`.

### 2. Empty `action` parameter is not defaulted (Low/Medium)
**Location:** `dispatch()`, the line `$action = is_string(...) ? $params['action'] : 'default'`.

**Problem:** `?controller=document&action=` produces `_action`. The old code treated an empty action as `default`.

**Fix:** Use `$action = ($params['action'] ?? '') !== '' ? … : 'default'`.

### 3. `_state` comparison changed from loose to strict (Medium: behavior change)
**Location:** `if ($controllerObj->_state === false)`.

**Problem:** The old code used `== false`, so `null`, `0` and `''` also short-circuited after the process step. If any controller leaves `_state` unset/null (or sets it to 0) to signal "stop", the new code now runs the display action after processing. That could re-render or double-execute logic.

**Fix:** Either confirm every `C_*` controller sets a strict boolean, or keep the loose semantics.

### 4. Parameter collisions in `act()` (Medium)
**Location:** the `act()` loop that copies the remaining parameters.

**Problems:**
- An explicit `action` key is renamed to `sub_action`, but an explicit `controller` key is not. A request like `?document&view&controller=prescription` silently overwrites the positionally selected controller. The ACL check does run on the final value, so this is not an ACL bypass, but the routing is confusing and surprising.
- Integer keys are compared with `===` against string-cast `$controller` / `$positionalAction`. For numeric query keys (e.g. `?5&…`), the routing keys are therefore not skipped and get passed again as arguments.

**Fix:** Handle `controller` the same way as `action` (rename it or reject it). Compare keys after casting both sides to string.

### 5. Argument semantics changed (Low/Medium)
**Location:** `dispatch()`, where `$args` is built and passed via `...array_values($args)`.

**Problems:**
- **Empty-value handling differs.** Only `''` is converted to `null`, whereas the old code used `empty() && != "0"`. The comment "matching act() behavior" is therefore inaccurate.
- **Argument names are no longer sanitized.** Positional mapping now depends on the full order of `$_GET`, including keys the old code would have stripped or ignored.
- **Unexpected values can crash typed actions.** A `sub_action` or array value can shift positional arguments or be passed into a typed parameter, causing a `TypeError` (500).

### 6. Uncaught HTTP exceptions in a legacy entry point (Medium: reliability / information disclosure)
**Location:** the `throw new BadRequestHttpException` / `NotFoundHttpException` statements.

**Problem:** `controller.php` is a legacy script and is not obviously wrapped by a Symfony kernel or exception listener. Without a handler these become fatal "Uncaught exception" errors. With `display_errors` on, that includes stack traces and file paths.

**Fix:** Confirm a global handler exists that converts these exceptions to proper 400/404 responses, or catch them in `controller.php`.

### 7. Pre-existing: incomplete ACL coverage (Medium: security, pre-existing)
**Location:** `CONTROLLER_ACL_MAP`.

**Problem:** Only `practice_settings` and `prescription` are gated. `insurance_company`, `insurance_numbers`, `x12_partner`, `pharmacy`, `hl7`, `document`, `document_category` and `patient_finder` are now directly addressable via `controller=` with no central ACL check. They rely entirely on whatever (if any) checks exist inside each controller.

Previously, `pharmacy`, `insurance_company`, etc. were typically reached through `practice_settings`, which enforced `admin/practice`. Now they can be dispatched directly; the old code allowed this too, but the whitelist makes it an explicit, supported route.

**Fix:**
- Add ACL entries for these, e.g. `admin/practice` for `x12_partner`, `insurance_*` and `pharmacy`, and patient/document ACLs for `document*` and `patient_finder`.
- Consider default-deny: require every whitelisted controller to declare an ACL entry.

### 8. Minor / maintainability
- `act()` declares `non-empty-array` but does not enforce it. An empty `$_GET` emits an "undefined array key 0" warning before the `BadRequest`.
- The class now `implements ControllerInterface`, but none of the `C_*` subclasses are verified against it. The interface is not shown, so confirm it does not require methods the subclasses lack.
- `$_GET['process']` is still mutated globally from inside `dispatch()`. That side effect is surprising for a method that takes `$params` explicitly.