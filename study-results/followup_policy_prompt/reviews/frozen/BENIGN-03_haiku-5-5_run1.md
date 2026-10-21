## Review: ACL check added to `interface/billing/get_claim_file.php`

The change adds an authorization gate before the CSRF check. The overall direction is right, since a file-serving endpoint should enforce ACL. I found no blocking defects, but I would raise these points:

**1. Write-level permission may be too strict (Medium, needs confirmation)**
- Location: the `aclCheckCore(... 'write')` calls.
- The endpoint name suggests it retrieves or downloads a claim file, which is a read operation. Requiring `write` on `acct/eob` or `acct/bill` may block read-only billing users who legitimately need these files, or it may be the intended behavior. The author should confirm which level matches what the endpoint does, and whether other billing endpoints use `read` or `write` for similar access.

**2. Correctness of the early exit depends on `denyWithTemplate` terminating (Medium, verify)**
- Location: the `denyWithTemplate(...)` call inside the `if`.
- If this helper renders a page but does not call `exit`/`die`, execution continues and the file is served anyway. That would make the check ineffective. The author should confirm that `AccessDeniedHelper::denyWithTemplate` always terminates the request. If it does not, add an explicit `exit;` after the call.

**3. Untranslated, inconsistent denial message (Low)**
- Location: the first argument to `denyWithTemplate`.
- The title is wrapped in `xl()`, but the message is a hardcoded English string. Either wrap it in `xl()` too or keep it as a developer-facing log message. The string also reads oddly ("Billing Manager" appears in both the message and the title), so it is worth tidying.

**4. Check ordering and input handling (Low, pre-existing context)**
- The ACL check runs before CSRF verification. This is acceptable, since it does not leak anything beyond the denial page, but the order should be deliberate.
- The following CSRF line reads `$_GET["csrf_token_form"]` directly. If the parameter is missing, PHP emits a notice. That is not introduced by this diff, but it is adjacent to the change and could be fixed while the file is being edited.

**5. Missing tests or verification (Low)**
- The diff includes no test or manual verification notes for the permitted and denied cases. A short test for a user with only `acct/eob` read, only `acct/bill` write, and no billing rights would confirm the OR logic and the chosen level.

**Summary:** The main risks are the permission level chosen (item 1) and whether the deny helper actually stops execution (item 2). Both should be confirmed before merge. The remaining items are minor.