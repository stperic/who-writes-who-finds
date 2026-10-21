## Findings

### 1. Reflected/stored XSS via unescaped values in an inline script (fixed in principle, verification required)

- **Location:** `portal/portal_payment.php`, line ~91, the original `echo "<script>var jsondata='" . $edata['table_args'] . "';var ccdata='" . $edata['checksum'] . "'</script>";`
- **OWASP category:** A03:2021 Injection (XSS)
- **Problem:** The original code wrote database values into a single-quoted JavaScript string without any escaping. A `'` or `</script>` in `table_args` or `checksum` breaks out of the string or the script block and executes attacker-controlled JavaScript in the payment portal's origin. The change is the correct direction, but its safety depends entirely on `js_escape()`, whose definition is not in this diff.
- **Severity:** High as the code was before this change. **Low to Medium pending review of `js_escape()`.**
- **Verification needed:**
  - If `js_escape()` is `json_encode($v, JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT)` or equivalent, it is safe. It produces a quoted, fully escaped JS literal.
  - If it is `addslashes()`, `htmlspecialchars()`, or plain `json_encode()` without the `JSON_HEX_*` flags, it is **not** safe. `</script>` inside a JSON string still terminates the script block, so the XSS remains.
  - Confirm that the function returns a complete JS literal, including quotes, and does not depend on the surrounding quotes.

### 2. Encrypted payment data emitted to the browser (sensitive data exposure)

- **Location:** `portal/portal_payment.php`, the `ccdata` variable written into the page.
- **OWASP category:** A02:2021 Cryptographic Failures (sensitive data exposure); A04:2021 Insecure Design
- **Problem:** `$edata['checksum']` is the field the code decrypts into `$ccdata`, so it holds card or payment data. The change now sends that ciphertext to every client that loads the page, where it is visible in the HTML source, caches, logs, and any injected script. Ciphertext of card data should not leave the server, even though it is not plaintext. The client-side code also appears not to need it, since the decrypted data is used server-side. Only the decrypted fields the client actually needs should be sent, and card data should not be sent at all.
- **Severity:** Medium to High, depending on what the cipher protects and whether the value is used client-side. This is a PCI DSS concern.

### 3. Authorization of the `$edata` lookup cannot be verified (potential broken access control)

- **Location:** Code above line 88 (not shown in the diff), where `$edata` is loaded.
- **OWASP category:** A01:2021 Broken Access Control
- **Problem:** The payment page renders data for a record fetched from a parameter. Unless the query is scoped to the authenticated patient or session, an attacker who guesses or enumerates identifiers can read other records, including the payment-related fields above. The diff does not show this check.
- **Severity:** Unknown from the diff; High if the lookup is not scoped to the current user.

### 4. Cryptographic implementation not visible (`decryptStandard`)

- **Location:** `$cryptoGen->decryptStandard(...)`, line ~89.
- **OWASP category:** A02:2021 Cryptographic Failures
- **Problem:** The diff relies on `decryptStandard()`, and its mode, key management, and integrity checks are not shown. If it is unauthenticated (for example, AES-CBC without a MAC), the ciphertext could be tampered with. The decrypted output is also fed straight into `json_decode` without an error check.
- **Severity:** Unknown. Review the implementation for authenticated encryption (such as AES-GCM) and proper key handling.

### 5. Behavior change (not a vulnerability, but may break the client)

- **Location:** Same line as finding 1.
- **Problem:** The original code produced `var jsondata='{...}'`, a string. If `js_escape()` returns a quoted string, the client still receives a string, which is consistent. If it returns an unquoted JSON object, the client receives an object, which changes behavior for any script expecting a string. Confirm that the consumers of `jsondata` and `ccdata` still work.

## Summary

The change moves the page toward correct JavaScript output encoding, but its safety depends on `js_escape()`, which must be checked before merging. The larger concern is that encrypted payment data (`checksum`) is now delivered to the browser where it did not need to be. Also verify that the `$edata` lookup is scoped to the authenticated user.