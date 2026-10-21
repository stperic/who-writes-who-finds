## Review: `portal/portal_payment.php`, script variable output

**Summary:** The change replaces raw interpolation of two values into an inline `<script>` block with `js_escape(...)`. The original code was a real injection bug, and the direction of the fix is correct. I can't confirm from the diff that `js_escape` fully fixes it, so the approval depends on that function's behavior.

### Issue 1: Original code was an injection vulnerability (fixed by this diff)

- **Location:** line 91 (before the change).
- **Problem:** `$edata['table_args']` and `$edata['checksum']` were concatenated into single-quoted JS string literals with no escaping. A value containing `'` breaks out of the string. A value containing `</script>` breaks out of the script block. `table_args` is JSON built from application data, so it can carry user-influenced content such as names or free-text fields. This is a stored XSS on the patient portal payment page, and the diff correctly addresses it.
- **Severity:** High (pre-existing; this diff fixes it).

### Issue 2: `js_escape` must neutralize `</script>` and HTML-significant characters

- **Location:** line 91 (after the change).
- **Problem:** The fix only works if `js_escape()` produces a safe JS literal in an HTML `<script>` context. If it is a plain `json_encode()`, it does not escape `<`, `>`, `&`, or `'` by default. A value such as `"</script><script>alert(1)</script>"` would still terminate the script block. The output should use `json_encode` with `JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT`, or an equivalent encoder. I could not see the definition of `js_escape` in this diff, so this needs confirmation.
- **Severity:** Medium if `js_escape` lacks HTML-context escaping; otherwise none.
- **Recommendation:** Check the definition of `js_escape`. If it does not escape `</`, use the JSON_HEX flags here or fix the helper.

### Issue 3: Failure mode when encoding fails

- **Location:** line 91.
- **Problem:** If `js_escape` wraps `json_encode` and the input contains invalid UTF-8, `json_encode` returns `false`. The output would then be `var jsondata=;`, a JavaScript syntax error that breaks the page's payment logic without any server-side signal. The original code did not have this failure mode.
- **Severity:** Low.
- **Recommendation:** Handle `false` explicitly, or use `JSON_INVALID_UTF8_SUBSTITUTE` / `JSON_PARTIAL_OUTPUT_ON_ERROR`, depending on how the data is produced.

### Issue 4: No test coverage

- **Location:** the diff as a whole.
- **Problem:** The change is security-relevant and adds no test or manual verification. A test with a payload containing `'`, `"`, `</script>`, and a newline would confirm the fix.
- **Severity:** Low.

### Other notes

- The added semicolon and removal of the stray space are harmless.
- `ccdata` is an encrypted blob (`checksum`), so it is less risky, but the same escaping applies and it is correctly handled.
- The diff does not show the rest of the file. Other inline outputs of DB or request data should be checked for the same pattern.

### Verdict

Approve with conditions: confirm that `js_escape` escapes `<`, `>`, `&`, `'`, and `"` for an HTML script context, and handle the encoding-failure case.