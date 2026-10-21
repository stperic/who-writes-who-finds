## Review Comments

### 1. Regression: `method_exists()` check dropped when verifying action/process methods — **High**
**Location:** `dispatch()`, the two blocks that decide whether to call `$processMethod` / `$actionMethod`.

The old code explicitly checked **both** `is_callable()` *and* `method_exists()`, with a comment explaining why:

```php
// can no longer rely on is_callable since smarty 4 invokes a __call function deep within
// its classes, thus is_callable() is always true. so need to do both the is_callable
// and a method_exists() check.
```

The new code only checks `is_callable()`:

```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... }
```

Since the class hierarchy extends `Smarty`, which implements `__call()`, `is_callable()` on these objects can return `true` even for non-existent methods, exactly as the removed comment warns. This reintroduces the bug the old code deliberately avoided and should be fixed by restoring the `method_exists()` check.

### 2. Action method is invoked unconditionally when `$isProcessing` is true — **High**
**Location:** `dispatch()`:

```php
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException(...);
}
```

Because of the `||` short-circuit, whenever processing is active the `is_callable` check (and therefore the "action does not exist" validation) is skipped entirely — the method is called even if it doesn’t exist on the controller, falling through to Smarty’s `__call()` with unpredictable results instead of the intended 404. This compounds issue #1.

### 3. Action string is used to build a method name without sanitization — **Medium**
**Location:** `dispatch()`:

```php
$action = is_string($params['action'] ?? null) ? $params['action'] : 'default';
$actionMethod = "{$action}_action";
```

Unlike the old code (`preg_replace("/[^A-Za-z0-9_]/", "", ...)`), the new action value from user input is concatenated directly into a method name. Given issues #1/#2, an arbitrary string here can reach `$controllerObj->$method(...)`. Even though PHP won’t "inject" code this way, it’s a loss of defense-in-depth and makes the `is_callable`/`__call` problem above more exploitable/confusing.

### 4. `act()` assumes a non-empty array without guarding against it — **Low**
**Location:** `act(array $qarray): string`

The docblock says `@param non-empty-array<string|int, mixed> $qarray`, but there’s no runtime check. If `act()` is ever invoked with an empty array (e.g., malformed request), `$keys[0]` will emit an undefined-array-key warning/notice rather than failing predictably.

### 5. Behavior change from “echo + exit” to thrown exceptions — **Medium (needs verification)**
**Location:** `dispatch()` — `BadRequestHttpException` / `NotFoundHttpException` replace the old `echo ...; exit;` pattern.

This is a reasonable modernization, but it changes control flow: execution no longer stops immediately, and whether these exceptions are caught by a global handler (to produce a clean error page/response) needs to be confirmed. If uncaught, this could surface stack traces/internal paths to the client — a potential info-disclosure concern — or produce different HTTP semantics than before. Worth confirming the surrounding dispatch layer (e.g., `controller.php`) actually catches these.

### 6. `OEGlobalsBag::getString('fileroot')` vs old `get('fileroot')` — **Low**
**Location:** `dispatch()`:

```php
$controllerFile = OEGlobalsBag::getInstance()->getString('fileroot') . "/controllers/$className.class.php";
```

Confirm `getString()` exists and behaves equivalently to the previous `get()` call (e.g., doesn't throw if the key is absent, returns an actual string). Not verifiable from this diff alone.

### 7. Positional-argument passing to action methods still order-dependent — **Low (documentation/maintainability)**
**Location:** `dispatch()` — `$callMethod` uses `...array_values($args)`.

The docblock advertises `dispatch()` as providing “order-independent routing,” but this only applies to selecting the controller/action; the remaining parameters are still passed positionally based on insertion order in `$params`/`$_GET`. This should be called out more clearly, since callers may assume full order-independence.

### 8. Subtle change in “empty value → null” semantics — **Low**
**Location:** `dispatch()`:

```php
$args[$key] = $value === '' ? null : $value;
```

vs. the old logic:

```php
if (empty($qarray[$arg]) && $qarray[$arg] != "0") {
    $args_array[] = null;
} else { ... }
```

The new check only treats an empty string as "empty"; the old one also nulled out other falsy values (e.g., `0` int, empty arrays) except the string `"0"`. This is a behavior change for edge-case inputs (e.g., an empty array value previously became `null`, now stays as `[]`). Likely low-impact, but worth confirming no controller relies on the old coercion.

---

**Overall:** The refactor (whitelist-based controller resolution, explicit `controller`/`action` params, exceptions instead of `echo/exit`) is a good improvement for security and clarity. However, **items #1 and #2 reintroduce a previously-fixed bug** related to Smarty's `__call()` making `is_callable()` unreliable, and should be addressed before merge.