## Review Comments

### 1. Regression: loss of `method_exists()` safeguard around Smarty's `__call()` quirk — **High**
**Location:** `dispatch()`, the process/action dispatch block.

The old code had an explicit comment:
> "can no longer rely on is_callable since smarty 4 invokes a __call function deep within its classes, thus is_callable() is always true. so need to do both the is_callable and a method_exists() check."

and therefore checked both `is_callable()` **and** `method_exists()`:
```php
if (is_callable([&$c_obj, $c_action . "_action_process"]) && method_exists($c_obj, $c_action . "_action_process")) {
```

The new code only checks `is_callable()`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... }
```
Given the documented Smarty behavior, `is_callable()` will likely always return true, meaning non-existent action methods will now be silently invoked (falling through to `__call()`), rather than throwing the intended `NotFoundHttpException`. This reintroduces a previously-fixed bug and defeats the new "action not found" error handling entirely.

### 2. `$action` is no longer sanitized before being used to build a method name — **Medium/High**
**Location:** `dispatch()`, `$actionMethod = "{$action}_action";`

Previously, both the controller and action segments were passed through `preg_replace("/[^A-Za-z0-9_]/", "", ...)`. The controller name is now safely constrained via the `VALID_CONTROLLERS` whitelist, but the action value is used raw. Combined with issue #1 (no `method_exists()` check), an attacker-controlled `action` parameter is concatenated directly into a dynamic method call that will fall back to Smarty's `__call()` magic method for virtually any value. This is at minimum a reliability regression, and potentially a security concern depending on what Smarty's `__call()` does with unrecognized method names/arguments.

### 3. Controller whitelist completeness is unverified — **Medium**
**Location:** `VALID_CONTROLLERS` constant.

Switching from "load any `controllers/C_*.class.php`" to an explicit whitelist is a good hardening improvement (previously, any controller file matching the naming convention was reachable via URL regardless of whether it was meant to be public). However:
- If any controller previously reachable via `act()` is missing from this list, functionality silently breaks (`BadRequestHttpException`/404 instead of working as before).
- Conversely, if a new/internal-only controller is ever added here without equivalent ACL coverage, it becomes publicly reachable. This whitelist needs to be kept in sync with actual files and access requirements — worth a comment/test ensuring parity.

### 4. ACL coverage gap (pre-existing, but directly touched by this change) — **Medium (security)**
**Location:** `CONTROLLER_ACL_MAP`.

Only `practice_settings` and `prescription` get ACL checks; the other 8 whitelisted controllers (`document`, `document_category`, `insurance_company`, `patient_finder`, `pharmacy`, `x12_partner`, etc.) have no ACL check at this layer at all. This mirrors the pre-existing behavior, but since this PR refactors routing/ACL into a formal map, it's a good opportunity to flag that most controllers rely entirely on per-controller internal checks (if any) with no centralized enforcement. Worth confirming each of these controllers does its own ACL check internally; otherwise this is a latent access-control gap.

### 5. Uncaught exceptions may leak internal detail or crash ungracefully — **Medium**
**Location:** `dispatch()` — `throw new BadRequestHttpException(...)`, `throw new NotFoundHttpException(...)`.

The previous code used `echo ... ; exit;` which, while ugly, guaranteed no PHP fatal error. The new code throws Symfony HTTP exceptions. This requires every caller of `act()`/`dispatch()` (e.g. `controller.php` entry point) to be verified to catch these and render a proper error page. If any caller doesn't catch them, this becomes an uncaught exception resulting in a stack trace potentially shown to the user (information disclosure of file paths/class names) depending on `display_errors` settings. Please confirm there's a global exception handler/catch around all callers before merging.

### 6. Behavior change in empty-value handling — **Low/Medium**
**Location:** `dispatch()`, building `$args`:
```php
$args[$key] = $value === '' ? null : $value;
```
The old logic was:
```php
if (empty($qarray[$arg]) && $qarray[$arg] != "0") { $args_array[] = null; } else { $args_array[] = $qarray[$arg]; }
```
This treated `0`, `false`, `null`, and `""` as "empty" (converted to `null`), except literal string `"0"`. The new code only treats the empty string as null. Integer `0`/boolean `false` values (if any caller passes those) will no longer be converted to `null`, which could change behavior for controller methods relying on the old semantics. Worth explicit test coverage given this subtle difference.

### 7. Side-effect on superglobals inside `dispatch()` — **Low**
**Location:**
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```
This mutates `$_GET`/`$_POST` directly even though the method now accepts an explicit `$params` array — this undermines the stated goal of "order-independent, explicit" routing and makes `dispatch()` harder to unit test or call with arbitrary non-`$_GET` arrays (behavior will silently depend on global state). Pre-existing issue carried forward, but should be cleaned up as part of this refactor rather than preserved.

### 8. Silent swallowing of non-string return values — **Low**
**Location:** `$callMethod` closure:
```php
$result = $controllerObj->$method(...array_values($args));
return is_string($result) ? $result : '';
```
If an action method returns a non-string (e.g., array/int by mistake), this is now silently discarded as an empty string rather than surfacing a type error/warning as before. This could mask bugs in controller action implementations during development.

### 9. Fragile `action` → `sub_action` renaming in `act()` — **Low (maintainability)**
**Location:** `act()`:
```php
$params[$key === 'action' ? 'sub_action' : $key] = $value;
```
This is explicitly a workaround for legacy "sub-controller delegation" patterns, as documented in the comment. It's reasonable as a transitional shim, but it is effectively undocumented outside this comment and relies on downstream controller code happening to read a positional argument correctly. Recommend adding targeted regression tests for the controllers that rely on this pattern (e.g., `practice_settings` → `pharmacy` → `list`) before merging, since this is exactly the kind of implicit convention that breaks silently.

### 10. Unverified API: `OEGlobalsBag::getInstance()->getString('fileroot')` — **Low**
Not shown in this diff; please confirm this method exists and returns a `string` (vs. the previously used `get()`). If it doesn't exist yet, this is a fatal error on every request through this code path.

---

### Positive notes
- Replacing the ad-hoc regex-based class name construction with an explicit `VALID_CONTROLLERS` whitelist is a solid security improvement over the previous "load any file matching the naming pattern" approach.
- Separating `dispatch()` (explicit, order-independent) from the deprecated `act()` (positional) is a good incremental step toward cleaner routing, provided issues #1/#2 above are fixed before merge.