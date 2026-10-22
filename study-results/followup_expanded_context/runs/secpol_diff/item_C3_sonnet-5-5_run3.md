# Security review: `portal/portal_payment.php`

I found several serious issues. The worst are the new `recid` access-control hole, the CVV and card-number handling, and the exposure of `gateway_api_key` to the browser. I could not see `paylib.php`, `getPortalAuditRec()`, or the top of the file after `session_destroy()`, so some findings depend on those.

## High severity

**1. IDOR on the new `recid` parameter (new code)**
- Location: `$recid = (int)$_REQUEST['recid']` and `$edata = $appsql->getPortalAuditRec($recid)`.
- OWASP: A01 Broken Access Control.
- Problem: Any authenticated portal patient can pass an arbitrary `recid`. The code never checks that the audit record belongs to `$_SESSION['pid']` or that the user is staff. The record is decrypted (`decryptStandard($edata['checksum'])`) and rendered.
- Impact: A patient can read other patients' pending payment data: cardholder name, zip, expiry, last 4 digits, and the CVV (shown whenever `transId` is absent). If a record has `transId`, the full PAN is shown instead.
- Fix: Enforce `record.pid == session pid`, or restrict `recid` to staff sessions (`authUserID`).

**2. Patient can override the patient ID (pre-existing, relied on by the change)**
- Location: `$pid = $_REQUEST['pid'] ?? $pid; $pid = $_REQUEST['hidden_patient_code'] > 0 ? ... : $pid;`, plus `form_pid` from POST.
- OWASP: A01 Broken Access Control.
- Problem: The patient identity comes from request parameters and overrides the session identity.
- Impact: A portal user can view another patient's invoices, balances, and payment audit data. They can also post payments for another patient through `form_pid`.
- Fix: For portal sessions, always use `$_SESSION['pid']` and ignore request values.

**3. Payment-posting code is not restricted to staff**
- Location: `if ($_POST['form_save']) { ... ar_session / ar_activity inserts ... }`, and the `$_REQUEST['receipt']` path.
- OWASP: A01 Broken Access Control / A04 Insecure Design.
- Problem: The diff adds `$isPortal`, but the posting block is not gated on a staff session (`authUserID`). A portal patient can POST `form_save`, `form_upay[...]`, and `radio_type_of_payment` directly.
- Impact: They can record payments, mark encounters closed (the `cash` option sets `last_level_closed=4` and `billed=1`), or create prepayments without paying. Amounts are not validated server-side, so negative or arbitrary values are accepted (`0 + $payment`, `form_prepayment`). The "negative payments" check exists only in JS.
- Fix: Require a staff session and validate amounts server-side (numeric, > 0, not above the balance).

**4. Payment gateway API key exposed to all users**
- Location: `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- OWASP: A02 Cryptographic Failures / A05 Security Misconfiguration.
- Problem: The key is emitted into the page for every gateway and every user. For Stripe, `gateway_api_key` is the secret key, so any portal user can read it and fully control the merchant account. Even for Authorize.Net, the page needs only the public client key and login ID. Print only what each gateway's client code requires, and only for that gateway.

**5. CVV and full PAN stored and displayed**
- Location: the `$ccdata["cardCode"]`, `$ccdata["cardNumber"]`, and `$ccdata["cc_number"]` handling in the display block; InHouse mode posts `cardNumber` and `cardCode` to `paylib.php`, which stores them in `onsite_portal_activity`.
- OWASP: A02 Cryptographic Failures / A04 Insecure Design.
- Problem: Storing the CVV after authorization is prohibited by PCI DSS. The full PAN and CVV are rendered to any staff member in clear text, and the PAN is rendered to anyone when `transId` is set. The `transId` field comes from the JSON the client submitted (`extra_values`), so the client controls which branch is taken.
- Fix: Use tokenization only (Stripe and Authorize.Net are already wired). Remove the InHouse flow or never persist the CVV, and always mask the PAN.

**6. Stored XSS via unescaped card number**
- Location: `echo $ccdata["cardNumber"] . "</span><br>";`, and the older `cc_number` equivalent.
- OWASP: A03 Injection (XSS).
- Problem: The `cardNumber` field is patient-controlled JSON (the client-side validator can be bypassed). It is echoed raw to staff, who then view it in an authenticated admin context. The other fields were switched to `text()`, but this one was missed.
- Fix: `text()` the value, and mask it before output.

## Medium severity

**7. No CSRF protection**
- Location: `invoiceForm` (posts `form_save`), the `paylib.php` AJAX and fetch calls, and the `paymentForm` form.
- OWASP: A01 / A04.
- Problem: None of these requests carries or verifies a CSRF token. A forged request could post payments in a staff session, or submit a payment from a patient's session.

**8. Client-controlled payment amount**
- Location: `$("#paymentAmount").val(total)`, the hidden `payment` field, `invValues`, and `form_paytotal` (readonly only in the UI).
- OWASP: A04 Insecure Design.
- Problem: Amounts and invoice data come from the browser. Unless `paylib.php` recomputes the balance from the database, a user can pay a tiny amount and have the invoice recorded as paid, or charge a different amount.

**9. Card data may still reach the server in the Authorize.Net flow**
- Location: `<form id='paymentForm' method='post' action='.../paylib.php'>` with `name="cardNumber"` and `name="cardCode"`.
- OWASP: A04 / A02.
- Problem: The design intends to keep card data off the server, but the form has no submit handler and a native action. Pressing Enter in a field submits the raw PAN and CVV to `paylib.php`. Even in the tokenized flow, the card inputs keep `name` attributes.
- Fix: Remove the `name` attributes from card inputs (Accept.js and Stripe Elements don't need them) and block native submit.

**10. Sensitive data handling in `inv_values` / `extra_values`**
- Location: `extra = "&inv_values=" + ... + "&extra_values=" + ...` in `paySubmit`.
- OWASP: A02.
- Problem: In InHouse mode, card data is sent twice: as form fields and in the JSON blobs (hence also in request logs and proxies if anything is logged). This is only safe over enforced TLS, and nothing here forces HTTPS.

## Low severity

**11. Audit trail and logging weaknesses**
- Location: the `user_id` / `post_user` values, and `sqlQueryNoLog`.
- OWASP: A09 Security Logging and Monitoring Failures.
- Problem: Records are attributed inconsistently: `$_SESSION['authId']` for the copay session, `$_SESSION['authUserID']` elsewhere, and a hardcoded `'3'` previously. For portal sessions these are null or wrong, so payments posted by a patient are unattributable. Viewing decrypted card data and `recid` lookups are not logged.

**12. Non-atomic sequence number generation**
- Location: `sqlBeginTrans(); SELECT MAX(sequence_no)+1 ... INSERT ...`.
- OWASP: A04 (data integrity).
- Problem: There is no `FOR UPDATE` lock, so concurrent postings can produce duplicate sequence numbers. The `sqlBeginTrans()` wrapper adds nothing without a locking read.

**13. JS-context escaping with `addslashes`**
- Location: `alert("<?php echo addslashes(xl(...)) ?>")`.
- OWASP: A03.
- Problem: `addslashes` is not safe for JS strings. Translation strings containing newlines or `</script>` can break out of the string. `json_encode` is already used elsewhere in the diff, so use it consistently.

**14. Third-party scripts and components**
- Location: jQuery and `jquery-creditcardvalidator` on a payment page; the Stripe and Accept.js scripts are loaded elsewhere.
- OWASP: A06 / A08.
- Problem: Confirm that the jQuery version is current and that external payment scripts are loaded from the official HTTPS origins. SRI is not applicable to Stripe, but check for it on the others.

**15. Pre-existing hygiene issues**
- Location: `$_POST['form_save']` and `$_REQUEST['hidden_patient_code']` used without `isset`, and user-supplied `form_method` and `form_source` stored without a whitelist.
- OWASP: A04.
- Problem: SQL is parameterized, so there is no SQL injection. But `form_method` should be validated against `list_options`, and error messages from `alert(data)` / `alert(error)` should be generic rather than echoing server output.

## Summary

SQL injection is avoided by the parameterized queries, and several outputs were improved from `attr()` to `text()`. I recommend not merging until items 1–6 are fixed, with item 3 confirmed against the unseen portion of the file.