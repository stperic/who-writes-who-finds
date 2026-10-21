# Security Review of Controller.class.php Pull Request

## Issues Found

### 1. **Broken Access Control - Incomplete ACL Coverage**
- **Location**: Lines 34-38 (`CONTROLLER_ACL_MAP` constant)
- **OWASP Category**: Broken Access Control
- **Problem**: The `CONTROLLER_ACL_MAP` only includes ACL checks for 2 controllers (`practice_settings`, `prescription`), but `VALID_CONTROLLERS` whitelist contains 9 controllers. The other 7 controllers (document, document_category, hl7, insurance_company, insurance_numbers, patient_finder, pharmacy) have no ACL enforcement. The `checkControllerAcl()` method silently returns if a controller isn't in the map (line 112), providing no access control.
- **Severity**: **HIGH** - Unauthenticated/unauthorized users can access sensitive controllers without ACL checks.
- **Recommendation**: Define ACL requirements for all whitelisted controllers in `CONTROLLER_ACL_MAP`.

---

### 2. **Injection - Unvalidated Action Parameter**
- **Location**: Lines 169-170 (action parameter and method name construction)
- **OWASP Category**: Injection (Code Injection/Method Invocation)
- **Problem**: While the controller name is whitelisted, the `action` parameter is only validated as a string but not against a whitelist. It's directly interpolated into method names (`"{$action}_action"` and `"{$action}_action_process"`) that are then called via `$callMethod()`. Although `is_callable()` is checked, a malicious actor could potentially invoke unintended methods if method naming patterns are predictable or if reflection-based attacks are possible.
- **Severity**: **MEDIUM** - Requires `is_callable()` check to pass, but action validation should be stricter.
- **Recommendation**: Implement a whitelist of valid actions per controller, or restrict action to `[A-Za-z0-9_]` pattern with length limits.

---

### 3. **Injection - Unvalidated Parameter Keys in Arguments Array**
- **Location**: Lines 174-181 (building `$args` array from params)
- **OWASP Category**: Injection (Potential Parameter Pollution)
- **Problem**: Parameter keys from `$params` are used directly without validation. While they're passed as argument names rather than evaluated as code, malicious keys could cause parameter pollution or unexpected behavior in downstream controller actions if those actions trust parameter names.
- **Severity**: **LOW** - Limited risk since keys are used as array indices, not evaluated. However, parameter name validation would be safer.
- **Recommendation**: Validate parameter keys against a whitelist of expected parameters or restrict to alphanumeric + underscore.

---

### 4. **Security Logging and Monitoring Failures**
- **Location**: Lines 112-119 (`checkControllerAcl()` method) and Lines 161-162 (controller loading)
- **OWASP Category**: Security Logging and Monitoring Failures
- **Problem**: ACL denials and access attempts are logged via `AccessDeniedHelper::denyWithTemplate()`, which is good. However, there is no logging for:
  - Invalid controller requests (line 162 throws exception silently)
  - Failed action method lookups (line 183 throws exception silently)
  - Successful controller instantiations or actions executed
  
  This makes it difficult to audit or detect abuse patterns.
- **Severity**: **MEDIUM** - Reduces observability of security events.
- **Recommendation**: Add structured logging for controller dispatch events, especially access attempts and failures.

---

### 5. **Insecure Design - Implicit Trust in OEGlobalsBag**
- **Location**: Line 167 (`OEGlobalsBag::getInstance()->getString('fileroot')`)
- **OWASP Category**: Insecure Design / Configuration
- **Problem**: The code assumes `OEGlobalsBag` is properly initialized and contains a safe `fileroot` value. If this value is ever user-controlled or improperly configured, it could lead to arbitrary file inclusion. Additionally, the code doesn't validate that the constructed `$controllerFile` path is within the expected directory.
- **Severity**: **MEDIUM** - Depends on OEGlobalsBag security; worth defensive programming.
- **Recommendation**: Add path validation to ensure `$controllerFile` is within `/controllers/` directory (e.g., `realpath()` check or disallow `../`).

---

### 6. **Vulnerable and Outdated Components Check**
- **Location**: Lines 5-6 (Symfony HttpKernel imports)
- **OWASP Category**: Vulnerable and Outdated Components
- **Problem**: No version constraints visible in the diff. `Symfony\Component\HttpKernel\Exception` classes are used, but without seeing `composer.lock` or `composer.json`, we cannot verify if vulnerable versions are in use.
- **Severity**: **INFORMATIONAL** - Requires full dependency audit (outside scope of this diff).
- **Recommendation**: Verify Symfony components are up-to-date and run `composer audit`.

---

## Summary

| Issue | Severity | Category |
|-------|----------|----------|
| Missing ACL checks for 7/9 controllers | HIGH | Broken Access Control |
| Unvalidated action parameter | MEDIUM | Injection |
| Unvalidated parameter keys | LOW | Injection |
| Insufficient security logging | MEDIUM | Security Logging & Monitoring |
| Missing path validation for controller file | MEDIUM | Insecure Design |

**Recommendation**: Do not merge until the HIGH severity ACL issue is resolved. All controllers in `VALID_CONTROLLERS` must have corresponding entries in `CONTROLLER_ACL_MAP`.