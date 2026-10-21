## Review Comments

### 1. Loss of `method_exists()` guard around `is_callable()` — **High/Critical**
**Location:** `Controller::dispatch()`, the two checks
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... } else { throw new NotFoundHttpException(...); }
```
The code being replaced had an explicit comment:
> "can no longer rely on is_callable since smarty 4 invokes a `__call` function deep within its classes, thus `is_callable()` is always true. so need to do both the is_callable and a `method_exists()` check."

This diff drops the `method_exists()` half of that check entirely. Since `Controller` extends `Smarty`, any `is_callable([$controllerObj, $method])` check may now return `true` even for undefined action/process methods, meaning:
- The `else { throw new NotFoundHttpException(...) }` branch for an invalid action may never actually trigger.
- Calling a non-existent `_action_process` method will invoke Smarty’s magic `__call()`, which can throw its own internal error or otherwise misbehave, for every controller action that doesn’t define a `_process` variant (a very common case).

This is a functional regression that reintroduces exactly the bug the removed comment was warning about. `method_exists($controllerObj, $method)` needs to be re-added to both checks.

### 2. Whitelist (`VALID_CONTROLLERS`) completeness risk — **High**
**Location:** `self::VALID_CONTROLLERS`
Previously any sanitized controller name could be loaded dynamically (`controllers/C_<Name>.class.php`). Now only the 10 listed controllers are reachable; any controller not in this map will hard-fail with `BadRequestHttpException`. If this list misses even one existing controller in `/controllers`, previously-working URLs/features silently break. Please verify this enumeration is exhaustive (ideally via a test that diffs the whitelist against the contents of the `controllers/` directory), since there’s no fallback path.

### 3. Uncaught Symfony HTTP exceptions from legacy entry point — **Medium**
**Location:** `dispatch()` — `throw new BadRequestHttpException(...)`, `throw new NotFoundHttpException(...)`
These exceptions assume something up the call stack (e.g. a Symfony kernel or a try/catch in the legacy `controller.php` entry script) converts them into proper HTTP responses. If the legacy entry point simply calls `act()`/`dispatch()` without catching these, an uncaught exception will surface as a raw PHP fatal error, which could leak stack traces (information disclosure) instead of the previous graceful `echo` + `exit`. Please confirm the caller handles these.

### 4. Hidden mutation of superglobals in `dispatch()` — **Medium**
**Location:**
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```
`dispatch()`’s docblock states it accepts a generic `$params` array “typically `$_GET`”, implying it can be called with arbitrary arrays (e.g. in tests or future callers). But it unconditionally reaches into and mutates `$_GET`/`$_POST` regardless of whether `$params` actually originated from them. This creates a surprising side effect and makes the method hard to unit test or reuse safely.

### 5. Changed "empty value → null" semantics — **Low/Medium**
**Location:**
```php
$args[$key] = $value === '' ? null : $value;
```
vs. original:
```php
if (empty($qarray[$arg]) && $qarray[$arg] != "0") { $args_array[] = null; } else { $args_array[] = $qarray[$arg]; }
```
The old code normalized any falsy value (except the string `"0"`) to `null` (e.g. `false`, `0`, `[]`). The new code only normalizes the exact empty string. For typical `$_GET`/`$_POST` string values this is probably equivalent, but if `dispatch()` is ever invoked with non-string params (int `0`, `false`, empty arrays), behavior now differs from the documented "matching `act()` behavior" comment. Worth double-checking downstream action methods that rely on `null` defaults.

### 6. Maintainability: duplicated bookkeeping for new controllers — **Low**
Adding a new controller now requires remembering to register it in `VALID_CONTROLLERS` (and `CONTROLLER_ACL_MAP` if ACL-gated), in addition to creating the controller file. This is reasonable as an interim step (per the TODO), but should be called out in contributor docs/CI to avoid silent breakage.

### 7. Minor robustness: unvalidated `$qarray` shape in `act()` — **Low**
**Location:** `act(array $qarray): string`
The docblock claims `@param non-empty-array`, but there’s no runtime check; calling with an empty array will raise "undefined array key" notices on `$keys[0]`/`$keys[1]`. Not a serious problem given upstream call patterns, but worth a defensive check given the explicit docblock contract.

---
No issues found with the ACL refactor itself (`checkControllerAcl`) — it's a faithful, cleaner extraction of the previous logic.