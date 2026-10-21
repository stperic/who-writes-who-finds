# Review: `library/auth.inc.php` session-timeout handling

**Verdict:** Approve, with minor follow-ups. I found no blocking issues. This change fixes a significant existing security flaw.

## The existing flaw this change fixes (High)

**Location:** the old condition `if (empty($skipSessionExpirationCheck) && empty($_REQUEST['skip_timeout_reset']))`

**Problem:** `skip_timeout_reset` comes straight from the request (`$_REQUEST`), so the client controls it. When it was present, the old code skipped the timeout check entirely, not just the timer reset.

- Anyone holding an expired session cookie could add `?skip_timeout_reset=1` (or POST it) to any request that includes `auth.inc.php`.
- That request would then be served as authenticated, even though the session had timed out.
- The inactivity timeout could therefore be bypassed at will. This matters for stolen or leftover session cookies, such as on shared clinic workstations.

**Fix:** The new code always runs `SessionTracker::isSessionExpired()`. The client flag now only controls whether the expiration timer is extended. That is the correct split:

- Background polling (Messages, Reminders, Flow Board) can still avoid keeping the session alive.
- Polling can no longer get around expiry.

I recommend noting this as a security fix in the changelog or release notes.

## Minor items

1. **AJAX and polling callers will now get a forced logout (Low, reliability).**
   - Polling endpoints that send `skip_timeout_reset` used to keep returning data after expiry. Now they will hit `authCloseSession()` and `authLoginScreen(true)`.
   - That call likely emits a login page or redirect, not the JSON these callers expect.
   - Please check that the JS pollers handle this response cleanly, either by detecting it and redirecting the top window to login, or by stopping polling quietly. They should not throw parse errors or inject login HTML into a widget.
   - This is the desired security behavior; the point is just to make the UI degrade cleanly.

2. **Confirm `authLoginScreen()` always terminates (Low, defensive).**
   - The expired branch relies on `authLoginScreen(true)` ending execution.
   - If any code path in that function returns without `exit`/`die`, the protected script would keep running after the session was closed.
   - Consider adding an explicit `exit;` after the call as a safeguard.

3. **`$skipSessionExpirationCheck` must never be settable from the request (Info).**
   - This variable now fully bypasses the timeout check.
   - It should only be set in trusted code, such as the login flow, before the include.
   - Please confirm nothing extracts request variables into scope (`extract($_REQUEST)`, `parse_str` without a target array, etc.) in any file that includes `auth.inc.php`.

4. **Tests (Info).** Please add or update a test that covers an expired session plus `skip_timeout_reset=1`. The expected result is a forced logout, which is exactly the regression this change closes.