## Review: `library/auth.inc.php` timeout logic refactor

**1. Behavior change for `skip_timeout_reset` requests (Medium)**
- **Location:** the `if (empty($skipSessionExpirationCheck))` block.
- **Problem:** Before, a request with `skip_timeout_reset` skipped the whole block. An expired session hitting a polling endpoint was left alone. Now those requests run `isSessionExpired()`, and if the session has expired they call `authCloseSession()` and `authLoginScreen(true)`. The commit message and comment don't mention this, so it reads as a timer-reset-only change.
- **Impact:** Background pollers (Messages, Reminders, Flow Board) will now force logouts and may receive login-screen HTML where they expected JSON or a small payload. The client code may not handle that, and it could produce confusing errors or repeated audit events. The new behavior may well be the right security posture, but it should be an explicit, documented decision. The PR should state it, and the polling callers should be checked or tested.
- **Suggested fix:** Confirm the intended behavior. If the logout is wanted, note it in the PR description and verify the AJAX callers handle a login-screen response. If not, keep the old skip for expired-session handling on these requests.

**2. Extra session-tracker query on every skip-flagged request (Low)**
- **Location:** `SessionTracker::isSessionExpired()` now runs even when `skip_timeout_reset` is set.
- **Problem:** Polling requests that previously did no session-tracker work now perform a lookup on every call. This adds database load on high-frequency endpoints.
- **Suggested fix:** Acceptable if intended, but worth measuring, or caching the result for the request.

**3. Unverified comment content (Low)**
- **Location:** the new comment names "the Flow Board" as a poller.
- **Problem:** The original comment named Messages and Reminders. Adding Flow Board is fine only if that caller actually sends `skip_timeout_reset`. Otherwise the comment is misleading.

**4. Pre-existing: `skip_timeout_reset` read from `$_REQUEST` (Informational)**
- The parameter is taken from GET/POST/cookies. It only suppresses the timer reset, so it is not a bypass, and the logic change above does not add a new exposure. Still, it is client-controlled, so no security decision should depend on it.

**Summary:** The refactor is clean and the non-skip path is unchanged. The main concern is item 1: the change alters how expired sessions are treated for background polling requests, which is a functional change that the diff does not describe. I would ask for that to be confirmed and documented, and for the polling callers to be tested, before merging.