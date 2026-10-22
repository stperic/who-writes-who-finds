## Review: controller dispatch refactor (`Controller.class.php`)

The refactor makes routing more explicit and adds a whitelist and ACL map. I found one correctness bug, one misleading claim in the docs, and several behavior changes that need checking.

### Issues

**1. Process-mode path calls the action method without checking it exists (Medium, bug)**
In `dispatch()`:
```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
```
When `$isProcessing` is true, the short-circuit skips `is_callable`. If `{$action}_action` does not exist, PHP throws a raw `Error` ("Call to undefined method") and the request fails with a 500. The `NotFoundHttpException` in the `else` branch is never reached in that case. The intent was clearly to check existence in both modes. The fix is to check `is_callable` unconditionally, for example `if (is_callable([$controllerObj, $actionMethod])) {...} else {throw ...}`.

**2. Arguments are passed by position, so the "order-independent routing" claim is false (Medium, correctness/doc)**
The docblock says URLs can use `controller=document&action=view&patient_id=123&doc_id=456` with order-independent routing. But the arguments go through `$controllerObj->$method(...array_values($args))`. The keys are discarded, so `patient_id` and `doc_id` are bound by their position in the query string. Reordering the parameters silently swaps the arguments. Either bind by name (for example, spread string keys with PHP 8.1+ named arguments, after validating them) or correct the documentation.

**3. Unvalidated action name builds the method name (Low, security/hardening)**
The old code stripped non-alphanumeric characters from the action name. The new code uses `$action` directly in `"{$action}_action"`. The `is_callable` check limits what can run in the normal path, but the process path (issue 1) has no check at all. Restoring a `preg_match('/^[A-Za-z0-9_]+$/', $action)` validation is cheap defense in depth.

**4. Error handling changed from output/exit to exceptions (Medium, reliability, needs verification)**
Unknown controllers and missing actions previously echoed a message (and `exit` for missing files). They now throw `BadRequestHttpException` and `NotFoundHttpException`. This is fine only if `controller.php` or a global handler converts these to HTTP responses. Otherwise users get a raw stack trace or a generic 500. Confirm the entry point catches them.

**5. `act()` compatibility and edge cases (Low)**
- `$keys[0]` on an empty array produces a warning. The `non-empty-array` annotation is not enforced. Add a guard.
- The legacy positional routing now maps keys in a different way (`action` is renamed to `sub_action`, and the second key becomes the action). Existing URLs such as `practice_settings&pharmacy&list` should be checked against this change.

**6. Behavior drift in the return handling (Low)**
- `$controllerObj->_state === false` was `== false` before. If `_state` is ever set to `null` or `0`, the early return no longer triggers. Confirm the type is always boolean, or restore the loose comparison.
- `$callMethod` now silently converts non-string return values to `''`. The old `.=` concatenation coerced them. A method returning `null` is now fine, but a method returning an object or number may lose output without any signal. Consider logging or matching the old coercion.

**7. Duplicated and hardcoded configuration (Low, maintainability)**
- `VALID_CONTROLLERS` and `CONTROLLER_ACL_MAP` duplicate knowledge already in the controllers. `C_PracticeSettings::__construct` still performs the same `admin/practice` ACL check, so the ACL rule now lives in two places.
- Sub-controllers such as `C_PracticeSettings` call `new Controller()->dispatch()`, which bypasses the outer controller's constructor-time ACL. That is safe only because the child controllers are listed in the map. Document this dependency.

**8. Global state mutation (Low)**
`unset($_GET['process'])` mutates a superglobal from inside `dispatch()`, which may be called recursively by sub-controllers. Removing `$_GET` mutation and relying on the `$params` copy would be cleaner.

**9. Test coverage (Low)**
The diff changes routing semantics substantially but adds no tests for: unknown controllers, missing actions in normal and process modes (issue 1), argument ordering (issue 2), the `act()` legacy mapping, and the `sub_action` delegation path.

### Summary
Issue 1 is a real bug and should be fixed before merge. Issue 2 is a correctness problem with the documented behavior. Issues 3 and 4 need fixes or verification. The rest are hardening and maintainability items.