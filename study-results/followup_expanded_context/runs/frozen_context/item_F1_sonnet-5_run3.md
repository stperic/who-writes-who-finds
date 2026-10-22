## Summary

This is a substantial refactor of legacy positional routing (`act()`) into an explicit `dispatch(array $params)` method, plus a `C_PracticeSettings` sub-dispatch pattern. The whitelist-based controller lookup (`VALID_CONTROLLERS`) is a genuine security improvement over the old "sanitize-and-include" approach. However, there are several correctness/reliability issues worth raising.

---

### 1. Dropped `method_exists()` check reintroduces a known Smarty bug — **High**
`Controller::dispatch()`:
```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) { ... } else { throw new NotFoundHttpException(...); }
```
The old code explicitly combined `is_callable()` **and** `method_exists()`, with a comment stating that Smarty 4's `__call()` makes `is_callable()` return `true` even for non-existent methods. This refactor only checks `is_callable()`. If that comment is still accurate, the `NotFoundHttpException` branch will effectively never fire, and invalid/unknown action names will silently fall through into Smarty's `__call()` magic method rather than producing a controlled 404. This defeats the purpose of the new validation and should be restored (`is_callable(...) && method_exists(...)`).

### 2. Uncaught HttpKernel exceptions change failure mode — **Medium**
`dispatch()`/`act()` now `throw new BadRequestHttpException(...)` / `NotFoundHttpException(...)` instead of echoing a message and `exit`. Nothing in this diff shows `controller.php` (or any global handler) catching `Symfony\Component\HttpKernel\Exception\HttpExceptionInterface` and converting it into a proper HTTP response. Outside an actual Symfony kernel, these exceptions will just propagate as uncaught PHP exceptions — producing a fatal error / stack trace (potential info disclosure in production) instead of the previous friendly error message. Please confirm the call site handles this, or catch-and-render here.

### 3. `dispatch()` mutates `$_GET` even when `$params` isn't `$_GET` — **Medium**
```php
if (isset($params['process'])) {
    unset($_GET['process']);
    unset($params['process']);
    $_POST['process'] = "true";
}
```
`dispatch()` is now a general-purpose, reusable method — e.g. `C_PracticeSettings::pharmacy_action()` builds its own ad-hoc `$params` array and calls `dispatch()` recursively. Unconditionally touching the `$_GET` superglobal inside a routing helper that may be invoked with unrelated/synthetic param arrays is a latent side-effect bug and a design smell. This should operate only on `$params`/`$_POST`, not reach into `$_GET`.

### 4. Loose → strict comparison changes behavior silently — **Low/Medium**
- `_state` check changed from `== false` to `=== false`. Any controller that previously set `_state` to a falsy-but-non-boolean value (e.g. `0`, `""`, `null`) will no longer short-circuit as before.
- Arg-normalization changed from PHP `empty()` semantics (treats `null`, `false`, `[]`, `0`, `""` as empty, except string `"0"`) to `$value === '' ? null : $value`. This changes what gets passed as `null` to action methods (e.g. `false`/`[]`/int `0` used to become `null`, now pass through unchanged). Worth confirming no existing controller action relies on the old semantics.

### 5. Duplicate/divergent ACL enforcement — **Low**
`Controller::CONTROLLER_ACL_MAP` now centrally enforces ACLs for `practice_settings` and `prescription`, but `C_PracticeSettings::__construct()` still performs its own `AclMain::aclCheckCore('admin', 'practice')` check independently. Having the same rule expressed in two places risks drift if one is updated and the other isn't. Consider removing the now-redundant in-constructor check or documenting why both are needed.

### 6. New controllers require manual whitelist/ACL registration with no enforcement — **Low (process risk)**
Adding a controller now requires updating `VALID_CONTROLLERS`, and separately remembering to add an entry to `CONTROLLER_ACL_MAP` if it should be restricted. Nothing fails loudly if a developer forgets the ACL entry — the controller just becomes reachable without an access check. Given this is now the single authoritative routing map, consider a stronger convention (e.g., requiring every controller class to declare its own ACL requirement via `ControllerInterface`) so a missing ACL isn't a silent omission.

### 7. Fragile positional-argument correlation preserved across two layers — **Low (maintainability)**
`act()` renames `action` → `sub_action` to avoid collisions for sub-controller dispatch, and `dispatch()` then rebuilds `...array_values($args)` based on `$params` iteration order. This still depends on query-string key ordering lining up with the target method's positional parameters (as acknowledged by the inline comment), just now split across two methods instead of one. It works today given `C_PracticeSettings`'s calling conventions, but it's brittle and easy to break with a future change to parameter ordering.

---

### Positive notes
- Switching from `preg_replace`-derived filenames + blind `include_once` to an explicit `VALID_CONTROLLERS` whitelist is a solid security hardening.
- Clear separation of `dispatch()` (order-independent) from `act()` (legacy positional wrapper) with `@deprecated` tagging is good direction.