**Review of `portal/portal_payment.php` (inline script output)**

The change is correct and fixes a real problem. I found no blocking issues, only a few smaller points.

**What the change does well**
- Before, `$edata['table_args']` and `$edata['checksum']` were concatenated into a single-quoted JS string with no escaping. An apostrophe, newline, backslash, or `</script>` in the stored data would break the script or allow stored XSS. This is a security flaw in code the diff touches.
- `js_escape()` emits a properly quoted and escaped JS string literal, so the surrounding single quotes were correctly removed.
- The JS side still receives the same type, a string containing JSON, so existing client code that calls `JSON.parse(jsondata)` should keep working.

**Points to check or follow up**

1. **Confirm `js_escape()` escapes `<`, `>`, `&` (low to medium).**
   - `table_args` is attacker-influenceable data inside a `<script>` block. The escaping must neutralize `</script>` and `<!--`, for example with `JSON_HEX_TAG` or `\u003C`.
   - If the helper is plain `json_encode` without those flags, a `</script>` in the data could still end the script element. The helper's behavior is not visible in this diff.
   - Please verify this, or add a small test with a payload like `</script><script>alert(1)</script>`.

2. **Encrypted card data is still sent to the browser (low to medium, pre-existing).**
   - `$edata['checksum']` is the encrypted cardholder data blob. Sending it into page JS widens its exposure through caching, browser extensions, and any other XSS.
   - Consider keeping it server-side and referencing it by an opaque ID. If the client does need it, document why.

3. **Unchecked decryption and JSON results (low, pre-existing).**
   - `json_decode($cryptoGen->decryptStandard(...))` and `json_decode((string)$edata['table_args'])` are not checked for failure.
   - If decryption fails, `$ccdata` and `$invdata` become `null`, and later code may emit warnings or behave incorrectly.

4. **Maintainability (nit).**
   - The script block is echoed from PHP. It would be cleaner to render it in a template, or to put the data in a `data-*` attribute escaped with `attr()`, instead of using globals (`jsondata`, `ccdata`) set from inline script.
   - The line also lacks a trailing semicolon after the last statement. It is harmless but inconsistent.

5. **Related sinks (low).**
   - Other places in this file that echo DB or request values into HTML or JS should be audited for the same unescaped pattern. This diff only fixes one line.

**Verdict:** approve, conditional on confirming point 1. Points 2 and 3 are worth tracking as follow-ups.