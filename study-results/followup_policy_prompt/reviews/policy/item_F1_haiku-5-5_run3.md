## Review: Controller routing refactor (`act()` → `dispatch()`)

The refactor moves routing to explicit `controller`/`action` parameters with a whitelist, which is a good direction. I found several behavioral regressions, one of which is a likely functional break.

### Issues

**1. High: `_state` check changed from `==` to `===`, changing control flow after process actions** (`dispatch()`, the `_state` check after `$processMethod`)

The original code used `if ($c_obj->_state == false) return $output;`. The new code uses `=== false`. `Controller::$_state` has no default value, so it starts as `null`. Under the old loose comparison, `null == false` is true, so output is returned after the `_process` method and the main action is skipped. Under the new strict comparison, `null === false` is false, so the main action now runs when a controller never sets `_state`. Any form-processing controller that relies on the old behavior will now execute its display action after processing. Restore `== false`, or make the intended semantics explicit and audit every controller that sets `_state`.

**2. High: `method_exists()` check removed; `is_callable()` alone is unreliable here** (`dispatch()`)

The original code explicitly noted that `is_callable()` is always true because Smarty 4 invokes `__call` internally, and it required `method_exists()` as well. The new code only uses `is_callable([$controllerObj, $actionMethod])`. For an unknown action, this may route into Smarty's `__call` instead of raising the intended `NotFoundHttpException`. Re-add the `method_exists()` check.

**3. High: Process path skips the existence check entirely** (`dispatch()`, `if ($isProcessing || is_callable(...))`)

When `$isProcessing` is true, the code calls `$callMethod($actionMethod)` without checking that the method exists. A missing `*_action` method then produces a PHP fatal `Error` rather than the intended 404 exception. Check existence in every branch.

**4. Medium-High: Arguments are passed positionally in URL order, contradicting the "order-independent" claim** (`dispatch()`, `$callMethod(...array_values($args))`)

The docstring says routing is order-independent, but action arguments are spread with `array_values($args)`. The mapping depends on the order of keys in the query string, not on parameter names. For example, `action=view&doc_id=456&patient_id=123` would pass `456` as the first argument. Either pass named arguments, or bind by the action method's signature via reflection, or document that order still matters. As written, this is a silent correctness hazard for any action with more than one parameter.

**5. Medium: Action name is not sanitized** (`dispatch()`, `$actionMethod = "{$action}_action"`)

The old code stripped non-alphanumeric characters from the action name. The new code uses any string. `is_callable` limits what can run, but the input should be validated against `^[A-Za-z0-9_]+$` for consistency and defense in depth, especially given the `__call` concern above.

**6. Medium: Behavior change for process-only actions and output types** (`$callMethod`)

`$callMethod` coerces any non-string return to `''`. Previously, non-string output (for example, `null` or an object with `__toString`) was concatenated or failed differently. This is probably harmless but should be deliberate.

**7. Low-Medium: Empty-value handling diverges from the old `act()`** (`$args[$key] = $value === '' ? null : $value;`)

The old code converted any value where `empty()` was true, except `"0"`, to `null`. That included `[]`, `null`, and `false`. The new code converts only `''`. Note the comment still says "matching act() behavior", which is no longer accurate.

**8. Low-Medium: Error handling changed from `echo`+`exit` to uncaught exceptions** (`dispatch()`)

Callers, including `controller.php`, must now catch `HttpException`s or they will produce a 500 page. If debug mode is enabled, exception messages (which include controller names) may be exposed. Confirm the entry point handles these exceptions and that the messages are safe to show.

**9. Low: ACL coverage is partial and implicit** (`CONTROLLER_ACL_MAP`)

Only `practice_settings` and `prescription` have ACL checks in this layer. Other whitelisted controllers, such as `document`, `hl7`, `insurance_company`, `x12_partner`, and `pharmacy`, rely on their own internal checks. This matches the old behavior, but it is worth documenting, since the whitelist now makes it look like a full authorization boundary.

**10. Low: `$_GET`/`$params` inconsistency** (`isset($params['process'])` block)

The code unsets `$_GET['process']` but removes `process` from `$params`. If `dispatch()` is called with an array other than `$_GET`, the two sources diverge. Also, `act()` with an empty array would produce `(string) null` and an undefined-index warning on `$keys[0]`, despite the `non-empty-array` annotation.

### Summary

The most important problems are #1 (`_state` strict comparison, which changes whether the main action runs after processing), #2 (`method_exists` removed, which can misroute to Smarty's `__call`), and #3 (missing existence check on the process path). #4, the positional argument mapping, contradicts the stated design and should be fixed or documented before merge. The rest are maintainability and robustness concerns.