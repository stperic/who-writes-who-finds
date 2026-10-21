## Review Comments

### 1. `dispatch()` — `is_callable()` check no longer paired with `method_exists()`
**Location:** `Controller::dispatch()`, the process/action invocation block.

```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... } else { throw new NotFoundHttpException(...) }
```

The old code had an explicit comment explaining that Smarty 4's `__call()` magic method makes `is_callable()` **always return true**, which is why the original logic required `is_callable() && method_exists()`. This refactor drops `method_exists()` entirely. As a result:
- The `NotFoundHttpException` "Action does not exist" branch is effectively dead code — `is_callable()` will basically always be true due to Smarty's `__call`.
- Invalid/undefined actions will silently fall through into Smarty's generic `__call` handler instead of producing a clean 404, which is exactly the bug the original comment was guarding against.

This is a reintroduction of a previously-fixed bug, and the explanatory comment documenting *why* this matters was deleted along with the fix. **Severity: Medium–High (correctness regression, loss of institutional knowledge).**

---

### 2. Action parameter is no longer sanitized before building a dynamic method name
**Location:** `dispatch()`, `$actionMethod = "{$action}_action";`

The old code sanitized both controller and action names with `preg_replace("/[^A-Za-z0-9_]/", "", ...)`. The controller name is now protected via the `VALID_CONTROLLERS` whitelist (good improvement), but the **action** name is taken from user input unsanitized and used directly to build a method name that is dynamically invoked (`$controllerObj->$method(...)`), and is also echoed back verbatim in exception messages (`"Action '$action' does not exist..."`). If these exception messages are ever rendered without escaping (debug pages, custom error handlers, etc.), this is a reflected-content/XSS vector. At minimum it's an unnecessary removal of input validation. **Severity: Low–Medium.**

---

### 3. Behavior change: exceptions replace `echo + exit`
**Location:** `dispatch()` — `BadRequestHttpException`, `NotFoundHttpException`.

The previous code failed "softly" via `echo ... ; exit;`. The new code throws Symfony HTTP exceptions. This is a reasonable modernization, but it changes the failure contract for every caller of `act()`/`dispatch()`. If any existing call site does not have exception-handling middleware around it, this will surface as an uncaught exception/fatal error instead of the old graceful message — potentially leaking stack traces (information disclosure) if `display_errors` is enabled, or producing an ugly 500 instead of a controlled error page. **Severity: Medium** — needs verification that all call sites are wrapped by a handler that converts these exceptions into proper HTTP responses.

---

### 4. `VALID_CONTROLLERS` whitelist completeness
**Location:** `Controller::VALID_CONTROLLERS`.

This is a good security improvement (previously any `C_<name>.class.php` file could be dynamically instantiated based on sanitized but otherwise unchecked input). However, it is a hardcoded, manually-maintained list. If any existing controller file is missing from this map, previously-working routes will now break with a `BadRequestHttpException`. The PR should confirm this list is exhaustive against the actual `controllers/` directory, and that there's a process to keep it in sync going forward. **Severity: Medium (regression risk).**

---

### 5. "Order-independent routing" claim is only partially true
**Location:** `dispatch()` docblock and argument building.

```php
$result = $controllerObj->$method(...array_values($args));
```

Only `controller` and `action` are truly order-independent (named). The remaining parameters are still passed **positionally** via `array_values($args)`, so the order in which extra query parameters appear still has to match the target method's parameter order. This doesn't fully deliver on "order-independent routing" and retains the fragility of the old positional-argument design. Worth clarifying in the docblock or improving with reflection-based named-argument binding. **Severity: Low (design/maintainability).**

---

### 6. Possible undefined-index access when `$qarray` is empty
**Location:** `act()`:

```php
$keys = array_keys($qarray);
$controller = (string) $keys[0];
```

If `act()` is ever invoked with an empty array, `$keys[0]` doesn't exist, triggering a PHP warning (and potentially a fatal error under strict error handlers). The old code guarded this with `array_key_first($qarray) ?? ''`. The `@param non-empty-array` annotation is not enforced at runtime. **Severity: Low.**

---

### 7. Superglobal mutation inside `dispatch()` based on caller-supplied `$params`
**Location:**
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```

This pre-existing pattern of mutating `$_GET`/`$_POST` as a side effect is carried over, but now `dispatch()` is presented as a general-purpose, reusable entry point (not just for `$_GET`-sourced calls). If `dispatch()` is ever called with a synthetic `$params` array (e.g., from tests or other internal callers) that happens to contain a `process` key, it will mutate real superglobals unexpectedly. This was a latent issue before but becomes more exposed now that `dispatch()` is a public, reusable API. **Severity: Low–Medium (hidden side effects / testability).**

---

### 8. Minor behavior change in null-coalescing of empty values
**Location:**
```php
$args[$key] = $value === '' ? null : $value;
```
vs. original:
```php
if (empty($qarray[$arg]) && $qarray[$arg] != "0") { $args_array[] = null; } else { ... }
```

The new check only treats an exact empty string `''` as "null-worthy," while the old one treated any falsy value (except the string `"0"`) as null. For typical `$_GET` string values the practical difference is small, but for array-valued parameters (e.g. `foo[]=`) or other edge cases, behavior now differs. Worth a quick sanity check/test to confirm no controller relies on the old `empty()` semantics. **Severity: Low.**

---

### Summary
The refactor is a solid modernization (whitelisting controllers, named `controller`/`action` params, exceptions instead of `echo+exit`), but it reintroduces a previously-fixed `is_callable()`/`__call()` bug (#1), drops action-name sanitization (#2), and changes error-handling semantics in a way that needs verification across all call sites (#3). The whitelist completeness (#4) and empty-array handling (#6) should be double-checked before merge.