## Review Summary

This diff actually **fixes** a pre‑existing authentication/session‑management flaw rather than introducing a new one. Below is the analysis.

### Previous (pre‑patch) vulnerability being corrected
- **Location:** `library/auth.inc.php`, old `if (empty($skipSessionExpirationCheck) && empty($_REQUEST['skip_timeout_reset']))` block
- **OWASP Category:** A01:2021 – Broken Access Control / A07:2021 – Identification and Authentication Failures
- **Problem:** The `skip_timeout_reset` request parameter — fully attacker-controlled via `$_REQUEST` — gated the *entire* session-expiration check, not just the "extend session" logic. Any request (even unauthenticated/forged) containing `skip_timeout_reset=1` would cause the code to skip `SessionTracker::isSessionExpired()` entirely, meaning a timed-out session would never be logged out as long as that parameter was present. This effectively allowed indefinite session validity, bypassing the timeout control.
- **Severity (historical):** High — this undermines session expiration, a core control against session hijacking/reuse.

### New code (this diff)
```php
if (empty($skipSessionExpirationCheck)) {
    if (SessionTracker::isSessionExpired()) {
        // force logout
    } elseif (empty($_REQUEST['skip_timeout_reset'])) {
        SessionTracker::updateSessionExpiration();
    }
}
```
- The expiration check (`isSessionExpired()`) is now always evaluated (subject only to `$skipSessionExpirationCheck`, which is set internally, not from user input in this snippet).
- `skip_timeout_reset` now only controls whether the expiration timer is *extended*, not whether expiration is *enforced*. This closes the bypass described above.

### Residual / minor observations (not blocking, low severity)
1. **Location:** `elseif (empty($_REQUEST['skip_timeout_reset']))`
   **OWASP Category:** A09:2021 – Security Logging and Monitoring Failures (minor)
   **Problem:** `$_REQUEST` mixes GET, POST, and COOKIE parameters. An attacker could trivially append `?skip_timeout_reset=1` to any link to prevent a victim's session timer from refreshing (causing them to be logged out sooner). This is a minor nuisance/DoS-of-convenience, not a security compromise, since it cannot extend or bypass authentication — but using `$_GET`/`$_POST` explicitly (and ideally a signed/trusted flag for internal polling endpoints) would be a defense-in-depth improvement.
   **Severity:** Low (informational).

2. No new injection, XSS, SSRF, deserialization, or crypto issues are introduced by this diff — the change is confined to control-flow around an existing method call.

### Conclusion
No new vulnerabilities are introduced by this diff. The change remediates a previously broken access-control/session-timeout bypass (A01/A07). One low-severity hardening suggestion (use explicit `$_GET`/`$_POST` rather than `$_REQUEST`) is noted but is not a merge blocker.