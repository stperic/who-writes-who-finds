**Issues found**

1. **Action name is no longer sanitized (security, medium-high).** `dispatch()`, `$action`
   - The old code ran `preg_replace("/[^A-Za-z0-9_]/", "", …)` on the action. The new code uses the raw `$_GET['action']` string to build the method name, and also stores it in `$controllerObj->_current_action`.
   - `_current_action` is used by `_link()` and templates to build URLs, so a crafted value can lead to reflected XSS or URL injection.
   - Any public method on the controller or on Smarty whose name ends in `_action` or `_action_process` can now be invoked.
   - Restore the whitelist regex, or validate with something like `/^[A-Za-z0-9_]+$/`.

2. **The `method_exists()` check was dropped, so "action not found" never triggers (correctness, high).** `dispatch()`, the `is_callable` branches
   - The removed comment said that `is_callable()` is always true on Smarty 4 because of `__call`, so `method_exists()` is also needed.
   - The new code uses only `is_callable()`. The `NotFoundHttpException` branch is therefore unreachable, and a bad action goes into Smarty's `__call` and fails obscurely.
   - The `$isProcessing || …` branch also calls the action unconditionally. A missing method then causes a fatal error instead of a 404.
   - Add `method_exists()` back to both checks.

3. **`act()` regresses when `process` is among the first two parameters (correctness, medium).**
   - The old code removed `process` from `$qarray` before it computed the controller and action from key order.
   - The new `act()` takes `$keys[0]` and `$keys[1]` first and leaves `process` to `dispatch()`. A URL like `?practice_settings&process=true&…` now treats `process` as the action.
   - Strip `process` from `$qarray` and `$_GET` before extracting the positional keys.

4. **Other edge cases in `act()` (reliability, low-medium).**
   - `$keys[0]` is read without checking for an empty array. The old code tolerated empty input; the new code raises an undefined offset warning and then a `BadRequest`.
   - PHP converts numeric-string keys to ints, so `$key === $controller` (int against string) can fail to skip the routing keys.

5. **Arguments are still positional, so the "order-independent" claim is false (design, medium).** `dispatch()`
   - The args are built from `$params` and spread with `array_values($args)`, so the order of query parameters still determines which argument each value lands in.
   - `controller.php?controller=document&action=view&doc_id=4&patient_id=1` passes the arguments swapped relative to `patient_id=1&doc_id=4`.
   - Bind by parameter name (reflection, or spreading with string keys as named arguments), and handle unknown parameters.
   - The missing-parameter case also no longer yields `null`, because absent keys are not padded.

6. **Behavioral changes that may break existing callers (maintainability and reliability, medium).**
   - Failures now throw `BadRequestHttpException` or `NotFoundHttpException` where the old code did `echo` and `exit`. Confirm that every caller (`controller.php` and others) catches these. Otherwise users see a 500 or a blank page.
   - The hard-coded `VALID_CONTROLLERS` list silently drops any controller not in it, such as module or custom controllers. Verify the list against `/controllers/C_*.class.php`.
   - `_state === false` is stricter than the old `== false`. A controller that sets `_state` to `0` or `null` no longer stops after the process step.
   - `callMethod` discards non-string return values, where the old code concatenated them.

7. **Minor issues.**
   - `$_POST['process'] = "true"` is still set from a GET parameter, which is a pre-existing CSRF-style weakness. It is worth a follow-up.
   - `dispatch()` unsets `$_GET['process']` but then reads `$_POST` globals, so it is not self-contained and is hard to test.
   - There is no test coverage for the new routing, ACL map or error paths.