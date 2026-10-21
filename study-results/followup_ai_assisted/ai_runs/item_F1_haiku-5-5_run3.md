## Review: controller dispatch refactor (`Controller.class.php`)

The whitelist and the ACL check are good improvements. I found one correctness bug that undermines the stated purpose of the change, one crash path, and several behavior changes that need verification before merge.

### 1. Arguments are passed positionally, so `dispatch()` is not order-independent (High)

**Location:** `dispatch()`, the `$args` build and `$callMethod` (`array_values($args)`)

The docblock says `dispatch()` provides "order-independent routing", with the example `controller=document&action=view&patient_id=123&doc_id=456`. But the arguments are collected into `$args` in URL order and then spread with `array_values($args)`. The controller action receives values by position, not by name. A request such as `?controller=document&action=view&doc_id=456&patient_id=123` would bind `doc_id` to the first parameter of `view_action()`, which is most likely wrong.

PHP 8 supports named arguments via string keys in a spread call. Passing `...$args` without `array_values()` would bind by name. That only works if the parameter names match the URL keys, so the action signatures and any related callers need checking. Either way, the current code does not deliver what the docblock promises.

### 2. A `process` request for a missing action method causes a fatal error (High)

**Location:** `dispatch()`, the final branch:

```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
}
```

When `$isProcessing` is true, the code calls `$actionMethod` without checking that it exists. If the controller has `foo_action_process` but no `foo_action`, this produces a PHP `Error` ("Call to undefined method") rather than the intended `NotFoundHttpException`. The original code guarded both branches with `method_exists`. The condition should be `is_callable(...)` for the action method, with the `$isProcessing` short-circuit removed.

### 3. Error handling changed from output-and-exit to exceptions (Medium)

**Location:** `dispatch()`, all `throw` sites

The old code echoed a message and called `exit` for an unknown controller or action. The new code throws `BadRequestHttpException` and `NotFoundHttpException`. Unless the entry point (`controller.php` or equivalent) catches these, users will get a generic 500 instead of the message. This is also a behavior change for any caller that relied on the output. Please confirm the front controller handles these exceptions.

### 4. The controller whitelist may remove previously reachable controllers (Medium)

**Location:** `VALID_CONTROLLERS`

The old `act()` loaded any `controllers/C_*.class.php` file that matched the URL. The new code only allows the ten listed names. Any controller present in `controllers/` but missing from the list is now unreachable. Please confirm the list is complete by comparing it with the directory contents and checking for any URLs or internal callers that use the removed names.

### 5. `act()` derives the action from the key name, not its value (Low to Medium)

**Location:** `act()`, `$positionalAction = (string) ($keys[1] ?? 'default');`

For a legacy URL such as `?practice_settings&action=list`, `$keys[1]` is the string `'action'`, so the action becomes `'action'` and dispatches to `action_action`. The `sub_action` rename in the loop only applies to non-positional keys, so it does not help in this case. The comment about `practice_settings->pharmacy->list` suggests this pattern is intended, so either the logic or the comment is inconsistent. Please add a test for this case.

### 6. Silent conversion of non-string return values (Low)

**Location:** `$callMethod`, `return is_string($result) ? $result : '';`

If an action returns `null`, an array, or any non-string value, the output is silently discarded. The old code concatenated with `.=`, so behavior differs. A `null` return from a non-rendering action will now be dropped without any warning. Consider logging or at least documenting this.

### 7. Empty input to `act()` (Low)

**Location:** `act()`

The docblock declares `non-empty-array`, but there is no guard. `$keys[0]` on an empty array emits a warning and casts `null` to `''`, which then produces a `BadRequestHttpException`. A guard with a clear error would be more predictable.

### 8. Minor points

- `isset($params['process'])` unsets `$_GET['process']` directly. If `dispatch()` is called with params that did not come from `$_GET`, the two sources get out of sync. Unsetting only from `$params` and setting `$_POST` would be cleaner.
- The `action` value is not validated beyond being a string. The `_action` suffix and `is_callable` limit the impact, so this is low risk, but a character whitelist (for example `/^[A-Za-z0-9_]+$/`) would match the sanitization the old code applied with `preg_replace`. The removed sanitization is worth restoring.

### Summary

| # | Location | Issue | Severity |
|---|---|---|---|
| 1 | `dispatch()` args | Positional args break the order-independence the change claims | High |
| 2 | `dispatch()` final branch | Process request with missing action method causes a fatal `Error` | High |
| 3 | `dispatch()` throws | Error output changed from message+exit to exceptions; verify handling | Medium |
| 4 | `VALID_CONTROLLERS` | Whitelist may make existing controllers unreachable | Medium |
| 5 | `act()` positional action | Key name used as action for `action=` patterns; logic/comment mismatch | Low–Medium |
| 6 | `$callMethod` | Non-string returns silently discarded | Low |
| 7 | `act()` | No guard for empty input | Low |
| 8 | `dispatch()` / action name | Minor sanitization and `$_GET` coupling | Low |

I recommend fixing items 1 and 2 before merge, and confirming items 3 and 4 with the front controller and the controllers directory.