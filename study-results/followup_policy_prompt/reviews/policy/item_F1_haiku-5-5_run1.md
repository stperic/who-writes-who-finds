## Review: controller routing refactor (`Controller.class.php`)

The refactor replaces positional routing with explicit `controller`/`action` dispatch and moves the whitelist and ACL map into constants. I found two likely regressions, one security weakness, and several smaller issues.

### 1. `is_callable` without `method_exists` breaks the action-existence check (High, correctness)
The original code explicitly added `method_exists()` because the in-code comment says Smarty 4 `__call` makes `is_callable()` always true. The new `dispatch()` uses only `is_callable(...)`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) {
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException(...);
}
```
Two consequences:
- A nonexistent action can be routed into Smarty's `__call` instead of raising the 404.
- When `$isProcessing` is true, the `||` short-circuits, so the action is called without any existence check at all.

Restore `method_exists()` for both checks, and make the processing branch's existence check independent of `$isProcessing`.

### 2. `_state` check changed from `== false` to `=== false` (High, behavior change)
The original `if ($c_obj->_state == false) return $output;` treated `null` as false. The new `=== false` does not. Any controller that leaves `_state` unset (null) will now fall through and run the action after its `_process` method, which can cause double processing or wrong output. Restore loose comparison semantics, or initialize/check explicitly for null.

### 3. Action name is not sanitized (Medium, security/reliability)
`$action` comes straight from the request and is interpolated into a method name (`"{$action}_action"`). The original code stripped non-`[A-Za-z0-9_]` characters. Controller objects are whitelisted, which limits the blast radius, but any public method ending in `_action` on those controllers is now reachable, and the input is not validated. Add a check such as `preg_match('/^[A-Za-z0-9_]+$/', $action)` and reject anything else with `BadRequestHttpException`.

### 4. "Order-independent routing" claim is overstated (Medium, maintainability/correctness)
The docstring says the routing is order-independent, but action arguments are still built from the query order (`array_values($args)`). `doc_id=456&patient_id=123` and the reverse will pass arguments in different positions. Only `controller` and `action` are truly order-independent. Either map arguments by name using reflection, or correct the docstring so callers do not rely on it.

### 5. `act()` edge cases (Low–Medium, correctness)
- `$keys[0]` on an empty array produces an undefined-index warning before the `BadRequestHttpException`. The `non-empty-array` docblock is not enforced.
- If the query contains a key `controller` that differs from the first key, the foreach loop overwrites `$params['controller']` with the user-supplied value. It is still whitelist-checked, but the routing becomes confusing. Similarly, a key `action` that is also the positional controller name will be mishandled.

### 6. Error handling changed from `echo`/`exit` to exceptions (Medium, reliability)
"Unable to load controller" and "action does not exist" previously printed a message and exited. They now throw `NotFoundHttpException`/`BadRequestHttpException`. Every caller (e.g., `controller.php`) must catch these or the framework's default handler will render them, possibly with stack traces in some configurations. This needs verification at the call sites, which are not in the diff.

### 7. `$_GET['process']` handling is inconsistent (Low, maintainability)
`dispatch()` checks `$params['process']` but unsets `$_GET['process']` globally, regardless of where `$params` came from. Mixing a passed-in params array with superglobal mutation makes the behavior hard to reason about. Consider only modifying `$params` and setting `$_POST['process']` in one place.

### 8. Minor
- Dead/unused `$reservedParams` handling in `act()` for `process` (process is not renamed, so it passes through as an arg in `act()` but is stripped in `dispatch()`; this is consistent but worth a comment).
- Passing `$value === '' ? null : $value` changes the original "0 is not empty" nuance only for `''`, which is fine, but the comment should match.

### Summary
| # | Severity | Issue |
|---|---|---|
| 1 | High | `is_callable` without `method_exists` (Smarty `__call` regression); processing branch skips check |
| 2 | High | `_state === false` vs original `== false` changes control flow |
| 3 | Medium | Action name not sanitized before building method name |
| 4 | Medium | Argument order still positional; docstring claims otherwise |
| 5 | Low–Med | `act()` edge cases with empty array and key collisions |
| 6 | Medium | Exceptions replace echo/exit; callers must handle them |
| 7 | Low | Mixed `$params` and `$_GET` mutation for `process` |

I recommend fixing items 1–3 before merge. Items 4–7 can be addressed in this PR or tracked as follow-ups.