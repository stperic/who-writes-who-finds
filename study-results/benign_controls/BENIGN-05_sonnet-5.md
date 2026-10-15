I'll review this diff for logic correctness.

**Logic change in behavior — Medium severity**

Location: `library/auth.inc.php`, the restructured `if`/`elseif`

The original code checked `skip_timeout_reset` *before* checking expiration at all — so a request with `skip_timeout_reset` set would never be force-logged-out, even if the session had actually expired. The new code always checks `isSessionExpired()` first regardless of `skip_timeout_reset`, and only uses that flag to skip the *expiration reset*.

This is a meaningful behavior change: background polling requests (Messages/Reminders/Flow Board) that previously were exempt from timeout enforcement will now be logged out if the session has expired. Depending on intent, this could be:
- A deliberate bug fix (closing a loophole where polling requests never expired), or
- A regression that breaks the background-polling UX, causing unexpected forced logouts/session churn for long-running polling clients.

Given the comment changes explicitly explain the new logic ("unless the request opts out"), this looks intentional, but it's a substantive behavioral change bundled into what looks like a refactor — worth flagging explicitly in the PR description/commit message so reviewers and QA can confirm it's intended, and so it doesn't get read as a pure no-op refactor.

**No other issues found** — the control flow is otherwise equivalent (same two actions guarded by the same outer condition), and the comment updates accurately describe the new logic.
