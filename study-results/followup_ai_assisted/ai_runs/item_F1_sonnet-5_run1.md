## Review Comments

### 1. Reintroduced bug: `is_callable()` without `method_exists()` — **High**
**Location:** `dispatch()`, the `$callMethod` invocation block.

The original code explicitly combined `is_callable()` **and** `method_exists()`:

```php
if (is_callable([&$c_obj, $c_action . "_action_process"]) && method_exists($c_obj, $c_action . "_action_process")) {
```

with the comment explaining *why*: Smarty 4's `__call()` makes `is_callable()` always return `true`, even for methods that don't exist. The refactor drops the `method_exists()` half of the check in both places:

```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... }
```

This silently reintroduces the exact bug that was previously fixed — any nonexistent action name will now appear "callable" (due to Smarty's magic `__call`), and the request will be routed into Smarty's internals instead of triggering the intended `NotFoundHttpException`. This needs to be restored.

### 2. Uncaught exceptions may regress error handling / leak info — **Medium**
**Location:** `dispatch()` — `throw new BadRequestHttpException(...)` / `throw new NotFoundHttpException(...)`.

The old code used `echo` + `exit` (ugly, but guaranteed a safe, controlled response). The new code throws exceptions. Nothing in this diff shows a global exception handler converting these into proper HTTP responses. If callers of `act()`/`dispatch()` (likely many legacy scripts across the app) don't catch these, this could result in unhandled exceptions/stack traces being shown to users — a potential information disclosure issue in a HIPAA-sensitive application, and a reliability regression. Please confirm there's a global handler (or that all call sites were updated) before merging.

### 3. Whitelist completeness risk — **Medium/High**
**Location:** `VALID_CONTROLLERS` constant.

Previously, controller name resolution was fully dynamic (`ucfirst` of each `_`-separated token), so any `C_*.class.php` file in `controllers/` could be loaded. Now only the 10 listed controllers are allowed. If any existing controller used elsewhere in the codebase isn't in this list, that feature will break with a `BadRequestHttpException` after this merges. Please audit all call sites of `act()`/`dispatch()` to confirm the whitelist is exhaustive.

### 4. Renaming `action` → `sub_action` changes positional-argument semantics — **Medium**
**Location:** `act()`:

```php
$params[$key === 'action' ? 'sub_action' : $key] = $value;
```

This silently changes what gets passed positionally into the resolved action method whenever the original `$qarray` contained a literal `action` key beyond the positional routing key (e.g., sub-controller delegation patterns like `practice_settings` → `pharmacy` → `list`). Any controller code relying on receiving that value as `action` (as a positional arg) will now get `sub_action` instead, and may silently receive `null`/wrong value where it expected the old key. This is a behavior change that isn't obviously safe without inspecting all consuming controllers — needs explicit verification/tests, not just a comment.

### 5. Silent discarding of non-string return values — **Low/Medium**
**Location:** `$callMethod` closure:

```php
$result = $controllerObj->$method(...array_values($args));
return is_string($result) ? $result : '';
```

Previously, the return value was concatenated directly (`$output .= $c_obj->{...}()`), so a non-string return (array, object, bool) would at least surface as a visible PHP warning/notice. Now it's silently swallowed into `''`. This could mask real bugs in action methods (e.g., a method that forgot to `return` a string, or returns `null` unintentionally) without any diagnostic trail.

### 6. Subtle change in "empty value → null" coercion — **Low**
**Location:** `dispatch()`:

```php
$args[$key] = $value === '' ? null : $value;
```

vs. original:

```php
if (empty($qarray[$arg]) && $qarray[$arg] != "0") { $args_array[] = null; }
```

These aren't equivalent for all falsy inputs (e.g. arrays, `false`, `"0"` edge cases already handled, but also values like `0` as int vs `"0"` string). Given this is used across many controllers with varying expectations, worth double-checking there's no observable behavior drift for edge-case values (e.g., array parameters from `$_GET`).

### 7. Misleading doc claim of "order-independent routing" — **Low (documentation nit)**
**Location:** `dispatch()` docblock.

The docblock states dispatch "provides order-independent routing," but this only applies to selecting `controller`/`action` from named keys. The remaining arguments are still passed **positionally** to the target action method via `array_values($args)`, so the actual argument order still depends on the iteration/insertion order of `$params` (e.g., query-string order). Worth clarifying in the docblock to avoid future confusion/misuse.

### 8. No validation of non-empty `$qarray` in `act()` — **Low**
**Location:** `act()`:

```php
$keys = array_keys($qarray);
$controller = (string) $keys[0];
```

The docblock claims `non-empty-array`, but this isn't enforced. An empty `$qarray` will trigger an "undefined array key 0" warning rather than failing cleanly/explicitly. Consider an explicit guard (`if (empty($qarray)) throw ...`) rather than relying on PHP warnings + downstream whitelist rejection.

---

**Summary:** The refactor is a solid improvement in structure (whitelist-based controller resolution, named-parameter dispatch, clearer exceptions), but **Issue #1 (dropped `method_exists()` check) is a real regression of a previously-fixed bug and should block merge** until restored. Issues #2–#4 should be verified against the rest of the codebase (call sites, downstream controllers) before merging, since they represent behavior changes not obviously covered by this diff alone.