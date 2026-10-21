# Security Review

I've identified **2 security vulnerabilities** in this pull request:

---

## 1. Broken Access Control - ACL Bypass via `act()` Method
**Location:** Lines 127-143 (the `act()` method)

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:** The `act()` method extracts the controller name from array keys via positional parameters and delegates to `dispatch()`. However, the controller name extraction at line 132 (`$controller = (string) $keys[0]`) does not validate against `VALID_CONTROLLERS` whitelist. If a caller invokes `act()` with malicious parameters structured to exploit the key-based extraction, they could potentially bypass the whitelist check that only happens in `dispatch()`. 

More critically, the `act()` method was the original entry point for ACL checks (lines in the old code checking `practice_settings` and `prescription`). The refactored code now defers this to `dispatch()`, but if legacy code paths or direct invocations of `act()` exist without subsequent `dispatch()` calls, ACL checks could be bypassed entirely.

**Severity:** High

---

## 2. Server-Side Request Forgery (SSRF) / Path Traversal via Unvalidated Controller Name
**Location:** Lines 165-167 (controller file loading in `dispatch()`)

**OWASP Category:** A10:2021 – Server-Side Request Forgery (SSRF) / A01:2021 – Broken Access Control

**Problem:** Although `dispatch()` validates the controller name against `VALID_CONTROLLERS` whitelist (line 154), the whitelist is incomplete. If an attacker can add a new entry to `VALID_CONTROLLERS` through code deployment or find an unintended whitelist entry, they could construct a path like `/controllers/C_EvilController.class.php` and trigger inclusion of arbitrary files within the controllers directory. 

Additionally, while `OEGlobalsBag::getInstance()->getString('fileroot')` appears to be trusted, there is no explicit validation that the resolved `$controllerFile` path stays within the intended controllers directory (no realpath comparison or directory containment check). A misconfiguration or symlink attack could potentially lead to arbitrary file inclusion.

**Severity:** Medium

---

## 3. Insecure Deserialization / Type Juggling Risk
**Location:** Lines 181-189 (argument building)

**OWASP Category:** A08:2021 – Software and Data Integrity Failures

**Problem:** User-supplied `$params` (typically `$_GET`) are passed directly into `$args` with minimal sanitization. While the code checks for empty strings (`$value === ''`), it does not perform type validation or encoding. If controller actions expect specific types (int, bool, etc.) but receive strings from URL parameters, this could lead to logic bugs. More critically, serialized objects or arrays in URL parameters could be instantiated in an unsafe manner if the controller uses unserialize() or other type-unsafe operations downstream.

**Severity:** Low to Medium (depending on downstream controller implementations)

---

## Recommendations

1. **Strengthen ACL enforcement:** Ensure ACL checks happen before any controller file loading, regardless of entry point. Consider removing or deprecating the `act()` method to enforce use of `dispatch()`.

2. **Add path validation:** Use `realpath()` and verify the resolved controller file is within the expected controllers directory:
   ```php
   $realPath = realpath($controllerFile);
   $allowedDir = realpath($fileroot . "/controllers");
   if (!$realPath || strpos($realPath, $allowedDir) !== 0) {
       throw new NotFoundHttpException("Invalid controller path");
   }
   ```

3. **Expand and document the whitelist:** Ensure `VALID_CONTROLLERS` is comprehensive and maintained as new controllers are added. Add a runtime validation that class_exists() and instanceof checks pass.

4. **Sanitize and validate parameters:** Add type hints and validation for controller action parameters where applicable.