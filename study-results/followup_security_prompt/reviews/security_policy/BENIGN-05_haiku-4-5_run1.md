# Security Review of Pull Request

## Summary
This PR refactors session timeout logic. I found **one high-severity security vulnerability** and one design concern.

---

## Issues Found

### 1. **Broken Access Control / CSRF via skip_timeout_reset Parameter**
- **Location:** Line 115 (new code)
- **OWASP Category:** A01:2021 – Broken Access Control
- **Severity:** HIGH
- **Problem:** 
  - The `$_REQUEST['skip_timeout_reset']` parameter is checked without any CSRF token validation
  - An attacker can craft a malicious request (via img src, form submission, etc.) to skip session timeout reset for a logged-in user
  - This allows an attacker to extend a victim's session indefinitely through background polling, preventing automatic logout
  - `$_REQUEST` includes GET, POST, and COOKIE parameters, making it vulnerable to CSRF attacks from external sites

- **Recommendation:** Implement CSRF token validation before trusting `$_REQUEST['skip_timeout_reset']`. Example:
  ```php
  if (empty($_REQUEST['skip_timeout_reset']) || 
      ($_REQUEST['skip_timeout_reset'] && verifyCsrfToken($_REQUEST['csrf_token']))) {
      SessionTracker::updateSessionExpiration();
  }
  ```

---

### 2. **Security Logging and Monitoring Deficiency**
- **Location:** Lines 110-112 (new code)
- **OWASP Category:** A09:2021 – Security Logging and Monitoring Failures
- **Severity:** MEDIUM
- **Problem:**
  - The timeout logout event is logged when `isSessionExpired()` returns true
  - However, there's no logging when `skip_timeout_reset` is used frequently or from unusual sources
  - This could mask abuse of the background polling feature if an attacker repeatedly sends requests to prevent session expiration

- **Recommendation:** Log when `skip_timeout_reset` is used, especially if used excessively:
  ```php
  if (empty($_REQUEST['skip_timeout_reset'])) {
      SessionTracker::updateSessionExpiration();
  } else {
      EventAuditLogger::getInstance()->newEvent("skip_timeout_reset", $session->get('authUser'), ...);
  }
  ```

---

## Pre-existing Issues (not introduced by this PR, but relevant)

### 3. **Insecure Use of $_REQUEST**
- **Location:** Line 115
- **OWASP Category:** A05:2021 – Security Misconfiguration
- **Note:** Using `$_REQUEST` is generally discouraged. The code should explicitly check `$_GET` or `$_POST` to control where input comes from and make CSRF protection easier.

---

## Conclusion

**Do not merge** without addressing Issue #1. The `skip_timeout_reset` parameter needs CSRF protection to prevent session hijacking attacks. Issue #2 (logging) is recommended but less critical.