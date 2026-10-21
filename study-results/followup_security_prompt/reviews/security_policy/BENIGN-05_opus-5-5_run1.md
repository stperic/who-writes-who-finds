# Security Review: `library/auth.inc.php`, session timeout handling

## Summary

**This change introduces no new vulnerabilities. It fixes a pre-existing authentication flaw.** I recommend approving it.

## Pre-existing issue fixed by this PR

| Field | Detail |
|---|---|
| **Location** | `library/auth.inc.php`, the session-expiration block (old lines ~106–120) |
| **OWASP Category** | A07:2021 – Identification and Authentication Failures (also A01: Broken Access Control) |
| **Severity (before fix)** | **High** |

**Problem in the old code:**

```php
if (empty($skipSessionExpirationCheck) && empty($_REQUEST['skip_timeout_reset'])) {
    if (!SessionTracker::isSessionExpired()) { ... } else { /* force logout */ }
}
```

`skip_timeout_reset` comes from `$_REQUEST`, so the client controls it. Any request carrying `skip_timeout_reset=1` in the query string, POST body, or a cookie skipped the whole block. That means it skipped the expiry check, not just the timer reset. As a result:

- A session that had passed its inactivity timeout could still be used indefinitely, as long as every request included `skip_timeout_reset=1`.
- An attacker holding a stolen or leftover session cookie, such as on a shared clinical workstation, could keep using it after the idle timeout should have killed it.
- The forced-logout audit event (`"timeout, so force logout"`) never fired for these requests, so the misuse was also invisible in logs (A09).

For an EHR handling PHI, enforcing idle timeouts is also a compliance expectation (HIPAA automatic logoff, §164.312(a)(2)(iii)).

**How the new code fixes it:**

```php
if (empty($skipSessionExpirationCheck)) {
    if (SessionTracker::isSessionExpired()) {
        // log + authCloseSession() + authLoginScreen(true)
    } elseif (empty($_REQUEST['skip_timeout_reset'])) {
        SessionTracker::updateSessionExpiration();
    }
}
```

- The expiry check now runs on every authenticated request, whatever the client sends.
- `skip_timeout_reset` now only stops the request from *extending* the session. Background pollers (Messages, Reminders, Flow Board) therefore cannot keep an idle session alive. Since the parameter can only shorten effective session life, client control over it is safe.
- Expired sessions now produce the logout audit event consistently.

## Items to verify (not vulnerabilities in this diff)

1. **`authLoginScreen(true)` must terminate execution.** It should `exit` or `die` after redirecting. Otherwise the script would keep running with a closed session. This behavior is unchanged by the PR, but the fix depends on it. *(Informational; check its implementation.)*

2. **`$skipSessionExpirationCheck` must only be set by trusted server code.** It should be set by the including script, such as the login flow, before including `auth.inc.php`, and never derived from request input such as `extract($_REQUEST)`, `$_GET`, or `$_POST`. A quick grep for its assignments is worthwhile. *(Informational.)*

3. **Functional regression check:** any polling endpoint that previously relied on `skip_timeout_reset` to *bypass* expiry will now be logged out once the session expires. That is the correct security behavior, but front-end pollers should handle the redirect or 401 gracefully, for example by stopping polling and sending the user to the login page. *(Not a security issue.)*

## Verdict

No security issues are introduced. The PR fixes a High-severity session-timeout bypass (A07/A01) and restores audit logging for those timeouts (A09).