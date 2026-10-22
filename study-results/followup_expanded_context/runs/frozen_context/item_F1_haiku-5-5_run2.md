## Review: refactor of `Controller::act()` into `dispatch()`

The refactor is well-intentioned: it adds a controller whitelist, moves ACL checks into a map, and replaces `echo`/`exit` with typed exceptions. However, I found several behavioral regressions that would change how existing controller actions run, so I would not merge this as written.

### Issues

**1. `method_exists()` check was removed, so unknown actions may not 404 (High)**
*Location:* `dispatch()`, the `is_callable([$controllerObj, $actionMethod])` check.
The original code deliberately checked both `is_callable()` and `method_exists()`, with a comment that Smarty 4's `__call` makes `is_callable()` always true. The new code keeps only `is_callable()`, so a nonexistent `foo_action` can resolve through Smarty's `__call` instead of reaching the `NotFoundHttpException` branch. Restore the `method_exists()` guard for both the action and process methods.

**2. `_state` check changed from `== false` to `=== false` (High)**
*Location:* `dispatch()`, the process branch.
`Controller::$_state` is declared without a default, so it is `null` unless a controller sets it. The original `$c_obj->_state == false` returns early when `_state` is `null`. The new `=== false` does not, so the action method runs after a process method that previously would have short-circuited. Restore loose comparison, or explicitly handle `null`.

**3. Arguments are passed positionally, contradicting "order-independent routing" (High)**
*Location:* `dispatch()` docblock and the `$args` construction.
The docblock promises that `controller=document&action=view&patient_id=123&doc_id=456` is order-independent, but the code does `...array_values($args)`, so arguments bind by query-string order. `doc_id=456&patient_id=123&...` would silently swap parameters. Either bind by name (e.g., reflection-based named arguments) or correct the documentation and keep the positional contract explicit.

**4. Whitelist and exception changes alter the external contract (Medium)**
*Location:* `VALID_CONTROLLERS`, and the `throw` statements replacing `echo ... exit`.
- Any controller file under `controllers/` not in the whitelist now fails, where it previously loaded. Confirm every existing caller and link is covered.
- Failures now throw `BadRequestHttpException` / `NotFoundHttpException`. Callers of `act()` and `controller.php` that expect the old `echo` output or no uncaught exception may now produce a 500 or an unhandled error. Confirm that an exception handler exists for this entry point.

**5. Action names are no longer sanitized (Medium)**
*Location:* `$action = ...; $actionMethod = "{$action}_action";`
The original code stripped everything except `[A-Za-z0-9_]` from controller and action names. The new code only checks `is_string()`, so arbitrary user input becomes a method name. `is_callable()` limits this to public methods, but the sanitization was defense in depth and should be kept.

**6. Process path skips the existence check for the action method (Medium)**
*Location:* `if ($isProcessing || is_callable(...))`.
When `$isProcessing` is true, the action method is called without any existence check, so a missing `_action` method produces a PHP fatal `Error` instead of the intended `NotFoundHttpException`. The `else` branch is also unreachable for processing requests.

**7. `act()` allows explicit query keys to override routing (Low)**
*Location:* `act()` parameter loop.
The loop skips only the positional controller and action keys. A query like `document&view&controller=pharmacy` writes `controller=pharmacy` into `$params`, overriding the routing key. ACL is evaluated against the overriding value, so this is not a bypass, but it is confusing and should reserve `controller`, `action`, and `process`.

**8. `act()` on an empty array (Low)**
`$keys[0]` on an empty array raises an undefined-offset warning before the `BadRequestHttpException` is thrown. Guard it explicitly. The `non-empty-array` docblock does not enforce this at runtime.

**9. Silent empty output for non-string returns (Low)**
`$callMethod` converts any non-string return to `''`. The old code concatenated whatever was returned. Controllers returning `null` are fine, but any other type is now silently dropped. Log or coerce it instead.

**10. Empty-value handling changed (Low)**
Old behavior mapped any value where `empty($v) && $v != "0"` to `null`. The new code maps only `''` to `null`, so `null`, `false`, and `[]` now pass through unchanged. Confirm that controllers relying on `null` for missing parameters still behave correctly.

### Summary
Issues 1, 2, and 3 are likely to change runtime behavior for existing controllers and should be fixed before merge. Issues 4 through 6 need verification or hardening. Items 7 through 10 are minor cleanup.