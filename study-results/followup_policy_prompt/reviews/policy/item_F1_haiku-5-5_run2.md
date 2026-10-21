## Review: controller dispatch refactor (`Controller.class.php`)

The refactor replaces the positional `act()` routing with a whitelisted `dispatch()`. The whitelist and the ACL map are good changes. I found one correctness bug that contradicts the code's own documentation, plus several behavior changes that need checking.

### Issues

**1. Argument mapping depends on query-string order. Severity: High (correctness)**

`dispatch()` builds `$args` from the params in insertion order and then calls `$controllerObj->$method(...array_values($args))`. Action methods therefore receive arguments positionally, in whatever order the URL lists them. The docblock says "order-independent routing", which is false.

Example: `controller=document&action=view&patient_id=1&doc_id=2` and `controller=document&action=view&doc_id=2&patient_id=1` pass the values in different positions. The second call can silently operate on the wrong patient or document, and it is easy to trigger from a crafted link.

Fix: map arguments by name. Either use named-argument spreading (`...$args` with string keys, PHP 8.1+) or use reflection to bind parameters by name. Either way the docblock and the implementation must agree.

**2. Error handling changed from echo/exit to exceptions. Severity: Medium (reliability/security, verify)**

The old code echoed a message and called `exit`. The new code throws `BadRequestHttpException` and `NotFoundHttpException`. Callers must catch these. If the front controller (`controller.php` or similar, not in this diff) does not catch them, users get an uncaught exception. Depending on `display_errors` and the error handler, that can leak file paths and stack traces. Confirm the caller handles these exceptions and returns a clean HTTP response.

**3. Legacy URLs and unlisted controllers stop working. Severity: Medium (backward compatibility)**

Previously any `controllers/C_*.class.php` could be reached through `act()`. Now only the ten whitelisted names are routable. Any bookmarked URL, custom module, or template that uses another controller will break. This is a security improvement, but the change should be called out and checked against all callers of `act()` and every `controller=` link in the codebase.

**4. `process` with no action method causes a fatal error. Severity: Low–Medium (reliability)**

The condition is `if ($isProcessing || is_callable([$controllerObj, $actionMethod]))`. When `$isProcessing` is true, the code calls `$actionMethod` without checking that it exists. A missing method then produces a PHP `Error` ("Call to undefined method") instead of the intended `NotFoundHttpException`. The check should be `is_callable` on the action method in both cases.

**5. `act()` lets a later `controller` or `action` key overwrite routing. Severity: Low (correctness)**

In `act()`, only the first and second keys are excluded from the copy loop, except for matches against those two names. A query such as `?document&action=view&controller=hl7` causes the later `controller` value to overwrite `$params['controller']`. ACL still matches what is dispatched, so this is not a bypass, but the routing is surprising. Reserved keys should be rejected or ignored explicitly.

**6. Empty-value semantics changed. Severity: Low (behavior)**

The old code turned any empty value except `"0"` into `null`. The new code converts only `''` to `null`. Other empty values, such as `[]` or `false`, now pass through unchanged. Check whether any action relies on the old behavior.

**7. Non-string return values are silently dropped. Severity: Low (maintainability)**

`callMethod` returns `''` when an action returns a non-string. Old code concatenated whatever came back. Any action that returns an array or null will now produce empty output with no warning, which makes such bugs hard to find. Log or assert on this case.

**8. ACL coverage is limited to two controllers. Severity: Medium (security, pre-existing)**

`CONTROLLER_ACL_MAP` covers only `practice_settings` and `prescription`. The other eight whitelisted controllers, including `document`, `hl7`, `pharmacy`, `insurance_company`, and `x12_partner`, get no ACL check at dispatch. This matches the old code, so it is not a regression, but the new whitelist makes the gap easy to see. Each controller should enforce its own ACL, or the map should be extended. The sub-controller delegation from `practice_settings` to `pharmacy` also needs checking.

**9. `process` flag can be set from GET. Severity: Low (security, pre-existing)**

`?process=true` on a GET request sets `$_POST['process']`, so state-changing `_action_process` methods can be triggered by a plain link. Those methods must check a CSRF token themselves. Confirm they do.

**10. Unverified dependencies. Severity: Info**

The diff uses `ControllerInterface`, `OEGlobalsBag::getString()`, and `xl()`. It also assumes `act()` and `dispatch()` match the interface's signatures. Confirm these exist and are compatible.

### Summary

The whitelist and ACL refactor are improvements. Issue 1 must be fixed before merge, since it makes the routing unsafe and contradicts its own documentation. Issues 2 and 3 need verification against the front controller and all callers. Issue 4 is a small fix. The rest are lower priority or pre-existing.