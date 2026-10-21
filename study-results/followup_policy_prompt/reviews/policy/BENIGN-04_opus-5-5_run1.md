# Review of `portal/portal_payment.php` (line ~91)

## Summary

The change is correct, and it fixes a real security bug. I recommend approving it, with a few follow-ups below.

## What the change fixes

**Stored XSS in `jsondata` / `ccdata` (pre-existing, High; fixed by this PR)**

Before this change, `$edata['table_args']` and `$edata['checksum']` were placed inside single-quoted JS string literals with no escaping:

```php
echo "<script>var jsondata='" . $edata['table_args'] . "';var ccdata='" . $edata['checksum'] . "'</script>";
```

`table_args` comes from the portal audit record, which holds JSON the patient submitted from the portal (invoice and payment data). A value containing any of the following could break out of the string or the `<script>` block:
- `'`
- `\`
- a newline
- `</script>`

That allowed script to run in the browser of whoever viewed the record. This includes clinic staff reviewing portal payments, which makes it a stored XSS that crosses from patient to staff.

Even harmless input broke the page. For example, a patient name with an apostrophe produced a JS syntax error.

**Why the fix works**

`js_escape()` is OpenEMR's `json_encode` wrapper. It produces a fully quoted, escaped JS string literal, so:
- The surrounding `'…'` quotes were correctly removed.
- `jsondata` and `ccdata` are still JS strings, so existing `JSON.parse(jsondata)` consumers keep working.
- The output is safe inside a `<script>` element.

## Issues and follow-ups

1. **Encrypted card data is sent to the browser** (Medium, security/PCI, pre-existing)
   - `ccdata` is the encrypted payment-card blob (`checksum`). The server already decrypts it into `$ccdata`.
   - It is unclear why the raw ciphertext needs to reach the client at all. The browser cannot decrypt it, and exposing it widens the attack surface. For example, it ends up in page caches and browser history snapshots.
   - Also confirm what this blob contains. Storing full PAN or CVV in the portal audit table, even encrypted, is a PCI-DSS problem. CVV must never be stored.
   - If no JS uses `ccdata`, remove the variable.

2. **Other output sinks for the same data** (Medium, security, pre-existing)
   - `$ccdata` and `$invdata` are decoded from the same attacker-influenced record and rendered later in this file.
   - Each echo of their fields should be checked for proper wrapping: `text()` / `attr()` in HTML and `js_escape()` in JS.
   - Do the same check in other templates that read `getPortalAudit(...)` / `table_args`, such as the portal review and dashboard views. Fixing only this one line leaves the same stored-XSS class open elsewhere.

3. **Authorization/scoping of `$edata`** (Low–Medium, verify)
   - Confirm that the audit record is fetched strictly by the session-bound `$pid` (patient portal) or by an authorized staff user.
   - It must not be fetched from a request parameter a patient can change. Otherwise one patient could load another patient's payment data, including the card blob.

4. **No error handling on decode** (Low, reliability)
   - `decryptStandard()` can fail and return `false`, and `json_decode` can return `null`.
   - The code then indexes into `$ccdata` / `$invdata` without checks, which causes PHP warnings or an empty form with no indication of what went wrong.
   - Check the decrypt result and handle the failure explicitly.

5. **Missing trailing semicolon** (Nit)
   - Add `;` after the `ccdata` assignment for consistency.

## Verdict

Approve. Please open follow-ups for items 1 and 2, since the same untrusted data is likely rendered unsafely elsewhere and card data handling deserves a closer look.