## Security review: `library/auth.inc.php`

**Result: no new security vulnerabilities found. This change improves security.**

### What changed

| | Before | After |
|---|---|---|
| Request has `skip_timeout_reset` | Skipped the **whole** block, including the expiry check | Still runs the expiry check and only skips the timer refresh |
| Request has no `skip_timeout_reset` | Checks expiry, then refreshes the timer or logs out | Same behavior |

### Analysis

**Fixed flaw (A01 Broken Access Control / A07 Identification and Authentication Failures).**
In the old code, `skip_timeout_reset` was read from `$_REQUEST`, so the client controlled it. Any request carrying `?skip_timeout_reset=1` bypassed `SessionTracker::isSessionExpired()` entirely. An expired session, or a hijacked or abandoned one, could therefore keep working against any endpoint that includes `auth.inc.php`, as long as the attacker added that parameter. The idle timeout was effectively optional. The new code always enforces expiry, and the parameter now only controls whether the timer is extended.

**Remaining client-controlled input, low risk.**
`skip_timeout_reset` is still attacker-controllable, but the only thing it can do now is stop the session from being extended. That fails closed, so it gives no advantage. It is not a vulnerability.

**Logging (A09).**
The timeout path still writes the `logout` audit event before closing the session, so monitoring is preserved. Polling requests that hit an expired session are now logged and forced to log out, which is the correct behavior.

**Control flow.**
The `elseif` structure is correct. Expiry is checked first, and the refresh happens only for non-expired sessions without the opt-out flag. This assumes `authLoginScreen(true)` terminates the request, as it did in the original code. Verify that it does, since that is unchanged and outside this diff.

### Non-security notes
- Background pollers (Messages, Reminders, Flow Board) will now trigger logout on expiry instead of silently continuing. This is intended, but check that the front-end handles a login-screen or redirect response to an AJAX call gracefully.
- Because polling no longer keeps the session alive, users who only have a polling page open will time out as designed.
- Consider adding a test that a request with `skip_timeout_reset=1` and an expired session is rejected, to prevent regression.

**Recommendation: approve from a security standpoint.**