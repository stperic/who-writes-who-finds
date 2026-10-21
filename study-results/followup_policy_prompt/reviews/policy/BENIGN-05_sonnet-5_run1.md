## Review Comments

**Location:** `library/auth.inc.php`, the restructured session-timeout block

**Issue (behavior change / compatibility risk):**
The old code only called `SessionTracker::isSessionExpired()` when **both** `skipSessionExpirationCheck` **and** `$_REQUEST['skip_timeout_reset']` were empty. That meant any request carrying `skip_timeout_reset` (the Messages/Reminders/Flow‑Board background polls) never had its expiration checked at all — these background calls could run forever without ever triggering a forced logout, even past the real timeout.

The new code always checks `isSessionExpired()` whenever `skipSessionExpirationCheck` is empty, and only uses `skip_timeout_reset` to decide whether to *refresh* the expiration timestamp. This is a more correct interpretation of "don't extend the session, but still enforce the timeout," and looks like an intentional (and reasonable) fix to a latent logic bug.

However, this is a meaningful behavior change for background/AJAX callers:
- Previously, Messages/Reminders/Flow-Board polling requests were effectively exempt from ever hitting the logout path.
- Now, if the session has actually expired, these background requests will hit `authCloseSession()` + `authLoginScreen(true)` — i.e., they will attempt to render/redirect to a full login screen in response to what is normally an XHR/JSON request.

This needs verification that all `skip_timeout_reset` call sites correctly handle a forced-logout response (e.g., detect an HTML/login payload and redirect the browser, rather than trying to parse it as JSON or silently failing). If the client-side polling JS isn't prepared for this, users could see broken UI behavior, console errors, or confusing partial page states when their session has actually expired while only background calls are occurring.

**Severity:** Medium — correctness/reliability concern; functionally this is likely the intended fix, but it changes externally observable behavior for several endpoints and should be confirmed against the JS/AJAX handlers consuming the login-screen response. Worth explicit test coverage and/or a changelog note.

---

**Other observations:**
- No new sanitization/escaping issues introduced by this diff.
- The security posture is arguably **improved**: expired sessions can no longer be kept alive indefinitely by only background requests, which is a legitimate fix to a previously under-enforced timeout. This should be called out as a positive, but confirm it doesn't unintentionally allow an attacker with an old/stolen session cookie to probe timeout status via background endpoints in a way the old code prevented (unlikely, but worth a quick think — not an issue found here).
- No automated tests were added/modified in the diff to lock in this new behavior (e.g., verifying that a `skip_timeout_reset` request is still forced to logout when expired). Low-severity maintainability gap.

If the AJAX endpoints already correctly handle forced-logout responses (many apps have a shared "session expired" interceptor), then this change is a clean bug fix with no outstanding issues.