## Review: `library/auth.inc.php` session timeout logic

**Issue 1: Behavior change for `skip_timeout_reset` requests (medium severity, needs confirmation)**

- **Location:** the `if (empty($skipSessionExpirationCheck))` block, specifically the `if (SessionTracker::isSessionExpired())` branch.
- **Problem:** In the original code, a request carrying `skip_timeout_reset` skipped the entire block, so it never checked for expiry and never logged the user out. In the new code, the expiry check runs for every request that isn't `skipSessionExpirationCheck`, including those with `skip_timeout_reset`. Background polling (Messages, Reminders, Flow Board) can now be the request that trips the timeout. It will call `authCloseSession()` and render `authLoginScreen(true)` into what is probably an AJAX or polling response.
- **Why it matters:** The PR title and comment describe only "don't reset the timer on polling," but the diff also changes whether polling can force a logout. That may be the intended outcome, since an idle user should be logged out even while a background poll is running. But it is a material behavior change that the description doesn't mention. Polling endpoints may not handle a login-screen response well, and the user could be logged out or see a broken widget with no clear cause.
- **Suggested action:** Confirm this is intended. If it is, state it in the PR description and check how the polling endpoints handle a login-screen response. If it isn't, restore the original structure so the expiry check is also skipped when `skip_timeout_reset` is set.

**Issue 2: Extra work on polling requests (low severity)**

- **Location:** the `isSessionExpired()` call.
- **Problem:** Polling requests now run `isSessionExpired()` on every call. If that method hits the database, it adds a query per poll that the old code didn't run.
- **Suggested action:** Check the cost of `isSessionExpired()`. This only matters if polling is frequent.

**Issue 3: Comment accuracy (low severity)**

- The comment says polling "from Messages, Reminders, or the Flow Board" is what opts out, but it doesn't mention that those requests are still subject to the timeout check. The comment should describe the new behavior: opted-out requests are checked for expiry but do not extend the session.

**Not an issue:** The restructured branches are logically equivalent for normal requests (not expired → update; expired → logout). The login-skip path is unchanged.

**Overall:** The restructuring is clean, but Issue 1 changes security-relevant behavior without a clear statement of intent. I'd request clarification or a description update before merging.