## Review: `library/auth.inc.php` session timeout logic

**Verdict: No exploitable vulnerabilities introduced. The change fixes a session-timeout bypass.**

### What changed

The old code wrapped the whole timeout block in `empty($_REQUEST['skip_timeout_reset'])`. A request carrying that parameter skipped both the expiration check and the timer reset. The new code runs `SessionTracker::isSessionExpired()` on every request that isn't explicitly exempted by `$skipSessionExpirationCheck`. The `skip_timeout_reset` parameter now only suppresses the timer reset.

### Security analysis

**Broken access control / Identification and authentication failures (A01, A07): fixed.**
Before this change, any request with `skip_timeout_reset=1` bypassed timeout enforcement. An attacker who obtained a session cookie could keep it alive past the idle timeout by sending that parameter on every request. The timeout could not expire for those requests at all. The new code enforces expiration on all non-exempt requests, so this bypass is closed.

**Reduced attack surface from the parameter.**
`skip_timeout_reset` is client-controlled, but it now only prevents the session from being extended. It cannot extend a session or bypass a check, so a client setting it only shortens its own session. No impact.

**Logging (A09): adequate.**
The timeout path still writes an audit event (`"logout"`, "timeout, so force logout") before closing the session.

**Injection, crypto, SSRF, integrity, misconfiguration, design:** No new issues. The diff contains no input handling beyond the existing `empty()` check, no crypto, no outbound requests, and no configuration changes.

### Behavioral side effects (not vulnerabilities)

- Background polling (Messages, Reminders, Flow Board) will now receive a login screen once the session has actually expired. This is the intended behavior, but the front end should handle it. Polling code that expects JSON or silently fails may behave oddly, and it may generate repeated login prompts in open tabs.
- Polling requests now execute `isSessionExpired()` on every call, which adds a database read per request. This is a performance consideration only.

### Items to verify before merge

1. **Fail-closed behavior:** Confirm `SessionTracker::isSessionExpired()` returns `true` (expired) when no `session_tracker` row exists for the session. If it returns `false` in that case, a missing row would disable timeouts.
2. **Control flow after `authLoginScreen(true)`:** Confirm this function calls `exit` (or otherwise terminates the request). If it returns, execution continues with a logged-out session.
3. **`$skipSessionExpirationCheck` source:** Confirm it is set only server-side (login flow) and cannot be influenced by `$_REQUEST` or other user input. If user input can set it, the bypass remains.
4. **Polling endpoints:** Confirm the AJAX endpoints that the comment names handle a redirect to the login screen gracefully.

### Severity summary

| Location | OWASP | Issue | Severity |
|---|---|---|---|
| `auth.inc.php`, timeout block (old version) | A01 / A07 | `skip_timeout_reset` bypassed session expiration entirely | High (fixed by this diff) |
| `auth.inc.php`, new version | — | No new vulnerabilities | None |

Approve, pending verification of items 1–3.