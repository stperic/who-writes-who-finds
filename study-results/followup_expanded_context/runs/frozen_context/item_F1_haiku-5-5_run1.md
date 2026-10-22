## Review: controller dispatch refactor

The refactor is reasonable in intent, but I'd block the merge on the first two issues below.

### 1. `practice_settings` is no longer routable (High, correctness)

`VALID_CONTROLLERS` does not contain `practice_settings`. A request to `controller.php?practice_settings&...` goes through `act()` into `dispatch()`, which throws `BadRequestHttpException`. The top-level Practice Settings page therefore breaks.

The `practice_settings` entry in `CONTROLLER_ACL_MAP` is consequently unreachable, so the ACL check the old `act()` performed for that route is dead code. `C_PracticeSettings` still performs its own ACL check in its constructor, so this is not a bypass, but the map entry suggests protection that does not exist. Add `practice_settings` to `VALID_CONTROLLERS` or remove the dead map entry, and add a test for the route.

### 2. Action existence check is wrong when processing (High, correctness)

```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
}
```

When `$isProcessing` is true, the short-circuit skips the existence check entirely. If `{$action}_action` does not exist, the call either fatals or hits a magic `__call`, instead of producing the intended `NotFoundHttpException`. The original code checked `method_exists()` in this branch too.

The code also relies on `is_callable()`, which the original comment explicitly warned is unreliable on Smarty 4 because of `__call`. Use `method_exists()` for the action and process checks, and only fall through to the not-found error when the method is missing.

### 3. Strict comparison changes the early-return behavior (Medium, behavior change)

The original code was `if ($c_obj->_state == false) return $output;`. The new code is `=== false`. If `_state` defaults to `null` or `0` on the base class, the original returned early and the new code continues to the action method. Either restore loose comparison or confirm the default is strictly `false`.

### 4. Exceptions replace `echo` and `exit` (Medium, reliability)

The old code printed a message and exited on an unknown controller or action. The new code throws `BadRequestHttpException` and `NotFoundHttpException`. Unless `controller.php` (not in this diff) catches these and renders a page, users get a 500 instead of the old message. Confirm the entry point handles them.

### 5. Argument mapping is still positional (Medium, maintainability)

The docblock says dispatch provides "order-independent routing", but `$controllerObj->$method(...array_values($args))` passes query parameters positionally in URL order. Parameter order still determines which value reaches which action argument, and a missing required argument raises `ArgumentCountError`. Extra parameters are silently ignored. Consider binding by name with reflection, or correct the docblock.

### 6. Smaller issues (Low)

- `callMethod` silently replaces non-string return values with `''`. The old code would have concatenated them, so a controller returning, for example, an int now produces empty output without warning.
- Query values can be arrays (`?x[]=1`), and these are passed straight into action methods, which may cause `TypeError`.
- `dispatch()` mutates the `$_GET` and `$_POST` superglobals, and nested dispatches from `C_PracticeSettings` share that global state.
- `act()` is documented as taking a `non-empty-array`, but it does not check for emptiness. An empty array yields an undefined-index warning before the BadRequest.
- The `key === 'action'` to `sub_action` rename is a subtle contract. It deserves a comment at the call site and a test covering the nested `practice_settings → pharmacy → list` path.
- No tests are included for the new routing, ACL, or exception behavior.

### Summary

| # | Location | Issue | Severity |
|---|---|---|---|
| 1 | `VALID_CONTROLLERS` / `act()` | `practice_settings` route now throws; its ACL map entry is dead | High |
| 2 | `dispatch()` action branch | `||` short-circuit and `is_callable` skip the existence check | High |
| 3 | `dispatch()` `_state` check | `== false` changed to `=== false` | Medium |
| 4 | Error handling | `echo`/`exit` replaced by exceptions; verify the caller catches them | Medium |
| 5 | Argument binding | Positional binding contradicts the "order-independent" claim | Medium |
| 6 | Misc. | Return-value dropping, array inputs, superglobal mutation, no tests | Low |