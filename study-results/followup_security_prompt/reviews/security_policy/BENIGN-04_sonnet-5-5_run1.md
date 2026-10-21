## Review of `portal/portal_payment.php`

### The change itself: fixes a vulnerability, no new issues

**Location:** line 91, the `echo "<script>var jsondata=..."` line
**OWASP category:** A03:2021 Injection (stored/reflected XSS)
**Severity of the original code:** High. The change fixes it.

The old code concatenated `$edata['table_args']` and `$edata['checksum']` into single-quoted JavaScript strings without escaping. Anyone who could influence those DB values could include a `'` or `</script>` and run script in the portal patient's session. That page handles payment data, so the impact would be serious. Using `js_escape()` (JSON-style encoding, with `/` escaped so `</script>` can't appear) is the right fix. The new code also emits proper quoted literals.

**Minor verification item (Low):** confirm that `js_escape()` in this codebase uses `json_encode` and that its output can't contain a literal `</script>`. Ideally it should also use `JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT`, which also neutralizes `<!--` script-data edge cases. If it does not, it is still very likely safe, but hardening is cheap.

### Pre-existing concerns in the code this change touches

1. **Sensitive payment data pushed to the client (A02 Cryptographic Failures / A04 Insecure Design) – Medium**
   - `ccdata` is the encrypted card blob (`$edata['checksum']`), echoed into the page's JS. Even though it is encrypted with a server-side key, there is no reason to expose it to the browser.
   - `table_args` (invoice data) is also dumped wholesale into the page.
   - Keep ciphertext and billing data server-side and reference it by an opaque ID, or send only the fields the UI needs.
   - Also check how the server decrypts and uses `checksum`. Any later round-trip where the client sends `ccdata` back and the server trusts or decrypts it would be a tampering or oracle risk.

2. **Authorization of the `$edata` lookup (A01 Broken Access Control) – needs verification**
   - The diff doesn't show how `$edata` is selected. Confirm that the query is bound to the authenticated portal user's `pid` from the session, not to a request parameter. Otherwise this is an IDOR that exposes another patient's payment data.

3. **Unchecked decryption/decode results (A04 / A09) – Low**
   - `json_decode($cryptoGen->decryptStandard(...))` and `json_decode($edata['table_args'])` aren't checked for failure, so `$ccdata` and `$invdata` can silently be `null`. Failures such as decryption errors or tampering should be handled and logged.

### Summary

The change correctly removes an XSS sink. No new vulnerabilities are introduced. Before merging, verify the `js_escape` implementation and the ownership check on `$edata`. Consider a follow-up to stop sending the encrypted card blob to the browser.