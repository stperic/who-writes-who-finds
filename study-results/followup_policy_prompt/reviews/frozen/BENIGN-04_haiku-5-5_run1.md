## Review: `portal/portal_payment.php` (inline script output)

**Overall:** The change is directionally correct. The old code wrapped raw values in single quotes, so any `'`, `\`, or newline in `table_args` or `checksum` could break the script or inject JavaScript. Switching to a dedicated escaping helper fixes that. However, the safety of the change depends on `js_escape()`, which is not shown in the diff, so I could not fully verify it.

### Issues

**1. `js_escape()` behavior is unverified (Medium, needs confirmation)**
- **Location:** line 91.
- **Problem:** The new code is only correct if `js_escape()`:
  - returns a complete JavaScript literal, including the surrounding double quotes. If it returns only the escaped body, the output becomes `var jsondata=...;` with no quotes, which is a syntax error. The consumer's `JSON.parse` logic would also break.
  - escapes for HTML-embedded script context. `table_args` is JSON from the database and can contain patient-entered text. Plain `json_encode` does not escape `</script>` or `<!--`, so a value containing `</script>` would still terminate the script block. The safe form needs `JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT`, or an equivalent escape of `<`, `>`, `&`, and U+2028/U+2029.
- **Suggestion:** Confirm the helper's implementation in the PR or a comment. Add a test with a payload containing `</script><script>alert(1)</script>` and a quote character.

**2. Encrypted checksum is sent to the browser (Low, pre-existing)**
- **Location:** line 91 (`ccdata`).
- **Problem:** The value is the encrypted payment data, and it is now emitted into the page. This is not introduced by the diff, but the escaping fix makes it a clear point to review. Confirm that this value is needed client-side and that it is not sensitive if exposed to the page context. If it is only needed server-side, it should not be emitted.

**3. Consumers may depend on the old string form (Low)**
- **Location:** the JavaScript that reads `jsondata` and `ccdata`.
- **Problem:** Previously both values were JavaScript strings. If `js_escape` produces a JSON string literal, they remain strings, so behavior is unchanged. If it produces a non-string literal (for example, an array or object), consumers would break. Confirm the output type matches what the readers expect.

**4. Minor: missing semicolon removed as a side effect (Info)**
- The original `ccdata='...'` had no trailing semicolon. The new version adds one, which is an improvement.

### Summary
The change is a reasonable hardening step. Before merging, confirm that `js_escape()` returns a quoted JavaScript string and is safe for embedding in an HTML `<script>` block, including protection against `</script>` in the data. The encrypted checksum exposure is a pre-existing concern worth a follow-up.