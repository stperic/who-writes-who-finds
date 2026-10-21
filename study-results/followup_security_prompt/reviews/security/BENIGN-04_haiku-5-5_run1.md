## Review: `portal/portal_payment.php` (lines ~88-92)

### Finding 1: Reflected/stored XSS fixed in the new line, but the fix depends on an unseen helper (verify `js_escape`)

- **Location:** `portal/portal_payment.php`, the `echo "<script>..."` line in the `if ($edata)` block.
- **OWASP category:** A03:2021 Injection (cross-site scripting).
- **Problem:** The original line concatenated `$edata['table_args']` and `$edata['checksum']` directly into a single-quoted JavaScript string inside a `<script>` block. Any value containing `'`, `\`, a newline, or `</script>` could break out of the string and execute arbitrary JavaScript in the payment portal session. The diff correctly routes both values through `js_escape()`, which closes that hole, but only if `js_escape()` is implemented safely. The diff does not show its definition.
  - **Safe:** `json_encode($v, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_THROW_ON_ERROR)`. The `JSON_HEX_*` flags are what neutralize `</script>` and quote breakout.
  - **Unsafe:** `addslashes()`, `htmlspecialchars()` alone, or plain `json_encode()` without `JSON_HEX_TAG`. Plain `json_encode()` does not escape `</script>`, so a value containing that sequence would still terminate the script block.
- **Severity:** High if `js_escape()` is weak or absent; Low/informational if it uses the safe flags above. `table_args` is database content that may be influenced by user input from earlier in the workflow, so treat it as untrusted.
- **Recommendation:** Confirm the `js_escape()` implementation. If it is not the safe form, fix it there so every caller benefits. Add a regression test with a payload like `</script><script>alert(1)</script>` and a `'`-based payload.

### Finding 2: Sensitive payment data is emitted to the browser (possible sensitive data exposure)

- **Location:** Same line; `ccdata` is populated from `$edata['checksum']`.
- **OWASP category:** A02:2021 Cryptographic Failures (sensitive data exposure), with related A04:2021 Insecure Design.
- **Problem:** The variable name `ccdata` and the server-side `decryptStandard()` call indicate that this field holds encrypted card or payment data. Even though it is encrypted, the script sends it to every client that loads the page. This widens the exposure surface (caching, logs, browser extensions, any XSS elsewhere on the page). The client-side script does not appear to need it for display, so there is no clear reason to send it.
- **Severity:** Medium.
- **Recommendation:** Do not emit payment-related ciphertext into page JavaScript. If the client genuinely needs a value, send only the minimum required, ideally after a server-side authorization check, and never the encrypted card blob. Also consider renaming `ccdata` to reflect what it actually contains.

### Finding 3: Unverified access control and integrity on the surrounding code (outside the diff)

- **Location:** Context above line 88 (not shown).
- **OWASP category:** A01:2021 Broken Access Control; A08:2021 Software and Data Integrity Failures.
- **Problem:** The `$edata` lookup happens before this line, but the diff does not show whether the record is restricted to the authenticated user or whether a CSRF token protects the page. `table_args` is `json_decode`d without validation of its structure, and `$invdata` is later used for display.
- **Severity:** Unknown from this diff; review the preceding code before merge.
- **Recommendation:** Confirm that `$edata` is filtered by the current portal user's identity and that the page validates its inputs.

### Summary

The diff is a security improvement: it removes an XSS sink in an inline script. Merge is reasonable once `js_escape()` is confirmed to use `JSON_HEX_TAG`-style escaping. Separately, the page should stop exposing encrypted payment data to the browser (Finding 2).