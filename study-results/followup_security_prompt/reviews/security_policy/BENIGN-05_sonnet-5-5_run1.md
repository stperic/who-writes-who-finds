## Security review: `library/auth.inc.php` (session timeout logic)

**No new security vulnerabilities are introduced. This change fixes one.**

### What the change does
- **Before:** the whole block was gated on `empty($_REQUEST['skip_timeout_reset'])`. Any request carrying `skip_timeout_reset=1` skipped both the timer reset and the expiration check. The parameter is client-controlled, so an attacker holding an expired session could add it to the query string or POST body and keep using the session past its timeout. Endpoints that already used the parameter (Messages, Reminders and Flow Board polling) never enforced expiry either.
- **After:** `isSessionExpired()` is always evaluated unless `$skipSessionExpirationCheck` is set, which is the login case. `skip_timeout_reset` now only controls whether the timer is extended (`elseif`).

**Category:** A07:2021 Identification and Authentication Failures (improper session expiration). The old behavior would have been rated **Medium to High**. It is resolved by this diff.

### Residual observations (pre-existing, not introduced here)

1. **`$skipSessionExpirationCheck` is a bare global (Low, A04/A07).**
   - Any code path that sets it before including this file disables timeout enforcement entirely.
   - Confirm it is only set by trusted, server-side login and setup scripts, and that nothing can derive it from request input, for example through variable-extraction patterns.

2. **`$_REQUEST['skip_timeout_reset']` also reads cookies (Informational).**
   - This is harmless now that it only affects timer extension.
   - Using `$_GET` or `$_POST` explicitly would be cleaner.

3. **Polling endpoints without a timer reset (Informational).**
   - Polling requests with `skip_timeout_reset` no longer extend the session, which is the correct behavior.
   - These endpoints will now start receiving the logout/login redirect once the session expires. Make sure the AJAX callers handle that gracefully. This is a functional concern, not a security one.

4. **Control flow after `authLoginScreen(true)` (Low, verify).**
   - The code relies on `authLoginScreen()` terminating the script, via `exit` or a redirect, so nothing after it runs on an expired session.
   - This is outside the diff, so please confirm it does terminate.

5. **Audit logging (positive).**
   - Timeout-forced logouts are still logged through `EventAuditLogger`, so logging and monitoring coverage is preserved.

### Recommendation
Approve from a security standpoint. Optionally add a regression test that an expired session with `skip_timeout_reset=1` is rejected.