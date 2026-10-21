# Security Review: `portal/portal_payment.php`

## Summary

This change **fixes a stored XSS vulnerability**, and the fix is correct. It should be merged. However, the surrounding code has a pre-existing design issue with cardholder data, and a few related areas outside the diff should be checked.

---

## 1. The change itself: stored XSS fix (approve)

**Location:** `portal/portal_payment.php`, line ~91
**OWASP:** A03:2021 – Injection (Cross-Site Scripting)
**Severity of the original bug:** High

**The original problem:**
`$edata['table_args']` is JSON built from the payment form a patient submits through the portal. The old code inserted it into a single-quoted JavaScript string with no escaping:

```php
echo "<script>var jsondata='" . $edata['table_args'] . "';...
```

A malicious portal user could submit a value containing `'` or `</script><script>...`. That payload would break out of the string and run arbitrary JavaScript in the browser of the **clinic staff member** who reviews the payment. Staff sessions have far more privileges than patient sessions, so this was a patient-to-staff privilege escalation path. It could lead to session theft, actions taken as the staff member, and access to PHI.

**Why the fix works:**
OpenEMR's `js_escape()` wraps `json_encode()` with the `JSON_HEX_TAG | JSON_HEX_AMP | JSON_HEX_APOS | JSON_HEX_QUOT` flags. As a result:
- The output is a complete, quoted JS string literal. This is why the manual `'...'` quotes were correctly removed.
- `<`, `>`, `&`, `'` and `"` are hex-escaped, so `</script>` breakout is not possible.
- `jsondata` and `ccdata` remain strings, as before. Downstream code that calls `JSON.parse(jsondata)` keeps working.

**Minor note (Low):** `json_encode()` returns `false` on invalid UTF-8. In that case, `js_escape()` outputs nothing, giving `var jsondata=;`, which is a JS syntax error. This is not exploitable, but it breaks the page. Consider validating the input when it is stored, or handling the failure explicitly.

---

## 2. Pre-existing issue: card data stored and sent to the browser

**Location:** Same block. Covers `$edata['checksum']`, the `$ccdata` decryption, and `var ccdata=...`
**OWASP:** A02:2021 – Cryptographic Failures / A04:2021 – Insecure Design
**Severity:** Medium–High (depends on what the checksum contains and on your PCI scope)

The `checksum` field holds encrypted card data from the portal payment form, and this page decrypts it with `decryptStandard()`. Several things follow from that:

- **Card data is stored in the application database**, even though it is encrypted. This puts the OpenEMR database and its key material in PCI DSS scope. If the card number, CVV, or both are stored, storing the CVV after authorization is prohibited outright.
- **The ciphertext is sent to the client** in `var ccdata`. That serves no clear purpose, because decryption happens on the server. It also exposes the blob to browser caches, extensions, and any XSS elsewhere on the page.
- **Decrypted card data appears to be displayed to staff** further down the page, which exposes the full card number in the UI.

**Recommendation:**
- Use a payment gateway's tokenization or hosted fields so that card numbers and CVVs never reach the server.
- If that is not possible right away, at least stop sending `ccdata` to the client, show only a masked number to staff, and delete the stored record once the payment is processed.

---

## 3. Items to verify outside the diff

These come from code that this block relies on but that is not shown in the diff. Please confirm them before merging.

**a. Authorization on the record lookup (possible A01:2021 – Broken Access Control)**
`$edata` is loaded from a portal audit record, typically identified by a request parameter such as `recid`. Confirm that:
- The lookup is limited to the current patient (`$pid`) when the request comes from the portal side.
- The staff-side view requires an authenticated user with the correct ACL, for example `acl_check('acct', ...)`.

If a portal user can supply any `recid`, they could view another patient's payment record and card data. This would be High severity.

**b. Other output sinks for the same data (A03:2021 – Injection)**
- Check whether `table_args` or `$invdata` fields are echoed anywhere else in this file without `text()` or `attr()`.
- On the JavaScript side, check whether parsed `jsondata` values are written into the DOM with `innerHTML`, `.html()`, or similar. That would be a DOM-based XSS that this fix does not cover.

**c. Logging (A09:2021 – Logging and Monitoring Failures)**
Make sure decrypted card data is never written to logs or audit tables in plaintext.

---

## Verdict

**Approve this change.** It correctly fixes a high-severity stored XSS that let a patient attack staff.

Separately, open follow-up tickets for:
- the card-data handling design (item 2)
- verifying authorization on the record lookup (item 3a)