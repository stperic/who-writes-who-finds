**Summary:** The change looks intentional and is mostly a good one. Requests with `skip_timeout_reset` previously bypassed the expiry check entirely, so an expired session could still be used by polling endpoints. Now only the timer reset is skipped. I have no blocking issues, but there are a few things to verify.

**1. Behavior change for `skip_timeout_reset` callers (Medium, needs verification)**
- Location: `library/auth.inc.php`, the new `if (SessionTracker::isSessionExpired())` branch.
- Problem: Every caller that passes `skip_timeout_reset` (Messages, Reminders, Flow Board, and possibly the client-side session-timeout or keep-alive check) can now trigger `authCloseSession()` and `authLoginScreen(true)`.
- These are usually AJAX requests. `authLoginScreen` emits a redirect or HTML login page and probably calls `exit`. A JSON or fragment consumer may break, loop, or render the login page inside a div.
- If any endpoint is meant to report remaining time or expiry without causing a logout, it will now log the user out instead.
- Suggestion: Audit all `skip_timeout_reset` users and confirm the front end handles the logout response. Consider returning a 401 or JSON for XHR requests.

**2. Audit-log noise and side effects (Low)**
- A background poll arriving after expiry now writes a "timeout, so force logout" event and destroys the session. This is probably correct, but several polls in flight at once, or from multiple tabs, may log duplicate events.
- Confirm that `authCloseSession()` is safe to call repeatedly.

**3. `$_REQUEST` as the opt-out source (Low, pre-existing)**
- `$_REQUEST` includes cookies and GET parameters, so any client can add `skip_timeout_reset=1` to avoid extending its session.
- This is low impact, since it only prevents extension. It is worth tightening to `$_POST` or `$_GET` if possible, or at least noting.

**4. No tests (Low)**
- There is no test covering the three paths: expired, valid with reset, and valid with `skip_timeout_reset`.
- This is security-relevant logic, so a regression test would be valuable.

**5. Comment quality (Nit)**
- The new comment is shorter and drops the explanation of why some requests skip the reset. The inline comment inside the `elseif` partly covers this.
- Consider also stating that the expiry check now applies to polling requests, so the change is discoverable later.