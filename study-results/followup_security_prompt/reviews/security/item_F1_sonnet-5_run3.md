## Security Review: `Controller.class.php` Refactor

### 1. Removed `method_exists()` safety check before dynamic method invocation
**Location:** `dispatch()` method, the block handling `$actionMethod` / `$processMethod` invocation.

**OWASP Category:** A01:2021 – Broken Access Control / A04:2021 – Insecure Design

**Problem:** The original code explicitly guarded dynamic method calls with **both** `is_callable()` and `method_exists()`, with a code comment explaining that `is_callable()` alone is unreliable because Smarty 4's `__call()` magic method makes it always return `true`:

```php
if (is_callable([&$c_obj, $c_action . "_action_process"]) && method_exists($c_obj, $c_action . "_action_process")) {
```

The new code drops the `method_exists()` check entirely:

```php
if ($isProcessing && is_callable([$controllerObj, $processMethod])) { ... }
...
if ($isProcessing || is_callable([$controllerObj, $actionMethod])) {
    $output .= $callMethod($actionMethod);
} else {
    throw new NotFoundHttpException(...);
}
```

Because of Smarty's `__call()`, `is_callable()` will return true for *any* action name, and when `$isProcessing` is true the `else` branch (which throws) is bypassed unconditionally. This means attacker-supplied `action` values that don't correspond to real methods are no longer rejected — they will silently fall through to Smarty's magic method handling instead of a controlled `NotFoundHttpException`. This removes a previously documented, intentional defense and reintroduces undefined/uncontrolled dispatch behavior.

**Severity:** High — this is a direct regression of a documented security control; actual exploitability depends on what Smarty's `__call()` does with arbitrary method names, but the control was removed without justification in the diff/commit.

---

### 2. HTTP Parameter Pollution — `controller` key can be overwritten, unlike `action`
**Location:** `act()` method, the loop that copies `$qarray` into `$params`.

**OWASP Category:** A01:2021 – Broken Access Control / A04:2021 – Insecure Design

**Problem:**
```php
foreach ($qarray as $key => $value) {
    if ($key === $controller || $key === $positionalAction) {
        continue;
    }
    $params[$key === 'action' ? 'sub_action' : $key] = $value;
}
```
The code special-cases a literal `action` key (renaming it to `sub_action` to avoid clobbering the positional action), but does **not** apply the same protection to a literal `controller` key. If the request contains an explicit `controller=...` parameter in addition to positional params, it silently overwrites `$params['controller']` that was derived from the first positional key. This is confusing/undefined behavior for a security-relevant routing decision, and indicates asymmetric/inconsistent input handling that could be exploited for parameter-pollution style routing confusion as the code evolves (e.g., if `act()` is later called with attacker-controlled query strings).

**Severity:** Medium — exploitation is limited today because `dispatch()` applies the whitelist/ACL check to whatever the *final* `controller` value is, but the inconsistent handling is a latent design flaw.

---

### 3. Centralized ACL map now implies coverage it doesn't provide
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`, combined with the newly introduced `VALID_CONTROLLERS` whitelist.

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** The refactor introduces a clean, centralized-looking ACL mechanism (`CONTROLLER_ACL_MAP`), but it still only covers 2 of the 10 whitelisted controllers (`practice_settings`, `prescription`). The other 8 (`document`, `document_category`, `hl7`, `insurance_company`, `insurance_numbers`, `patient_finder`, `pharmacy`, `x12_partner`) — several of which deal with PHI/PII (documents, insurance data, patient lookup) — have no access control enforced at this layer. This matches prior behavior, but the new, more "official-looking" ACL abstraction increases the risk that future maintainers will assume this map is the complete authorization story and forget to add entries for new/sensitive controllers, or will wrongly assume the other controllers are protected here rather than internally.

**Severity:** Medium (design/process risk) — recommend confirming (and ideally documenting/enforcing) that all other controllers perform their own authorization checks internally.

---

### 4. Information disclosure via exception messages
**Location:** `dispatch()`:
```php
throw new NotFoundHttpException("Unable to load controller: $className");
...
throw new NotFoundHttpException("Action '$action' does not exist on controller: $className");
```

**OWASP Category:** A05:2021 – Security Misconfiguration (Information Exposure, CWE-209)

**Problem:** Internal class names and action names are embedded in exception messages. Depending on how these exceptions are rendered to end users (stack traces, error pages), this could leak internal implementation details useful for further probing. Low impact since controller names are already a fixed, small, semi-public whitelist, but still worth sanitizing user-facing error output and ensuring exceptions are only logged, not echoed, in production.

**Severity:** Low.

---

### 5. Loss of defense-in-depth input filtering on method/argument names
**Location:** `dispatch()` — `$action` and `$args` keys are no longer passed through `preg_replace("/[^A-Za-z0-9_]/", "", ...)` as they were in the old `act()`.

**OWASP Category:** A03:2021 – Injection (weakened defense-in-depth) / A04:2021 – Insecure Design

**Problem:** While the new controller-name whitelist (`VALID_CONTROLLERS`) is a net improvement over the old regex-based filtering, the `action` value and parameter keys used to build `"{$action}_action"` / `"{$action}_action_process"` method names are no longer sanitized at all. Combined with issue #1 (loss of `method_exists()`), this removes a layer of input restriction that previously limited what strings could reach the dynamic method-name construction.

**Severity:** Low–Medium (mostly relevant as a contributing factor to issue #1).

---

## Summary Table

| # | Location | OWASP Category | Severity |
|---|----------|-----------------|----------|
| 1 | `dispatch()` dynamic method invocation | A01 Broken Access Control / A04 Insecure Design | **High** |
| 2 | `act()` param-copy loop (`controller` key) | A01 Broken Access Control / A04 Insecure Design | Medium |
| 3 | `CONTROLLER_ACL_MAP` coverage gap | A01 Broken Access Control | Medium |
| 4 | Exception messages leaking class/action names | A05 Security Misconfiguration | Low |
| 5 | Removed sanitization of action/param names | A03 Injection / A04 Insecure Design | Low–Medium |

The most important finding to fix before merge is **#1** — restore the `method_exists()` check (or an equivalent allow-list of permitted action method names per controller) before invoking `_action` / `_action_process` methods, since this was a deliberate, documented security control that has been silently dropped.