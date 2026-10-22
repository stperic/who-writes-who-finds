# Security review: `portal/portal_payment.php`

I found several serious issues. The most serious are the Stripe secret leaking to the browser, an IDOR that exposes stored card data, and unauthenticated-style payment posting by portal users.

## High / Critical

**1. Gateway secret key sent to the browser (Cryptographic Failures / Security Misconfiguration)**
- Location: new JS block, `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- `globals.inc.php` describes `gateway_api_key` as "Auth Name for Authorize.Net and **API Secret for Stripe**". The Stripe secret is therefore written into the page of every portal patient who opens the payment screen.
- The code needs only `publicKey` for Stripe. The Authorize.Net login ID does not need to be exposed either.
- Impact: anyone with a portal login can use the Stripe secret to issue charges and refunds and to read customer data on the merchant account.
- Severity: **Critical**. Remove `apiKey` from the client. Emit only the publishable key, and only for the gateway in use.

**2. IDOR on the new `recid` parameter (Broken Access Control)**
- Location: `$recid = (int) $_REQUEST['recid']; ... $appsql->getPortalAuditRec($recid);`
- The audit record is loaded by ID with no check that it belongs to the session's `$pid`.
- A portal patient can enumerate `recid` values and read other patients' pending payment records, including decrypted card data (`$ccdata`) and invoice data.
- The display logic makes this worse:
  - The full card number is shown to anyone when `$ccdata['transId']` is set.
  - Exp date and CVV are shown to non-staff viewers.
- Severity: **High**. Enforce `record.pid == $_SESSION['pid']` for portal users, and allow arbitrary `recid` only for authenticated staff.

**3. Patient identifier is attacker-controlled (Broken Access Control, pre-existing but relied on)**
- Location: `$pid = $_REQUEST['pid'] ?? $pid; $pid = $_REQUEST['hidden_patient_code'] > 0 ? ... : $pid;` and `$form_pid = $_POST['form_pid']`.
- A logged-in portal patient can pass any `pid`. They can then view another patient's balances, demographics and pending card data, and post payments against that patient's encounters.
- For portal sessions, `$pid` must be taken from `$_SESSION['pid']` only. `form_pid` must be checked against it.
- Severity: **High**.

**4. Payment posting has no authorization check (Broken Access Control / Insecure Design)**
- Location: `if ($_POST['form_save']) { ... }` writes to `ar_session`, `ar_activity`, `payments`, `form_encounter` and `billing`.
- The block is reachable by any portal-authenticated session. Only the template hides the "Post Payment" button for patients.
- A patient can POST `form_save` directly and mark their own invoices as paid. With `radio_type_of_payment=cash` they can close the encounter (`last_level_closed=4`) and mark billing as billed, without paying anything.
- `user_id`/`post_user` come from `$_SESSION['authUserID']` or `authId`, which are empty for portal users.
- Posting must be restricted to authenticated staff (`isset($_SESSION['authUserID'])` plus an ACL check).
- Severity: **High**.

**5. Stored XSS from the patient to staff (Injection / XSS)**
- Location: `echo $ccdata["cardNumber"] . "</span><br>";`, shown when `authUserID` is set or `transId` is set. The old code had the same flaw with `cc_number`.
- The value comes from patient-submitted JSON (`cardNumber`) stored in the audit table. It is printed without escaping to the staff user reviewing the payment.
- A patient can submit `<script>…</script>` as the card number and run script in a staff or admin session.
- Fix: `text()` the value, and validate server-side that it is digits only.
- Severity: **High**.

**6. Full PAN and CVV stored and displayed (Cryptographic Failures, PCI DSS)**
- Location: the "In House" gateway flow, which posts `cardNumber` and `cardCode` to `paylib.php`. The review panel prints them back: `$ccdata["cardNumber"]` and `$ccdata["cardCode"]` in `#cvvpin`.
- Storing the CVV after authorization is prohibited by PCI DSS. The PAN is shown in full to staff and kept in a reversible-encrypted DB field (`decryptStandard`).
- Sensitive card data is also placed in AJAX form bodies and JSON strings (`extra_values`, `inv_values`).
- Never persist or display the CVV. Mask the PAN. Prefer tokenization, as the Authorize.Net and Stripe paths do, and consider removing the In House option.
- Severity: **High**.

## Medium

**7. Payment amounts are trusted from the client (Insecure Design)**
- The paid total is computed in JS (`form_paytotal`, copied to the hidden `paymentAmount` field). `inv_values` is a client-built JSON blob that is forwarded to `paylib.php`.
- Server-side, `$amount = 0 + $payment` and `form_prepayment` are used as-is. Negative, zero and over-balance values are blocked only by JS (`calctotal`, `coloring`).
- Negative amounts or overpayments can corrupt the ledger. For gateway charges, the server must recompute the amount from invoice data.
- Severity: **Medium**. I could not verify `paylib.php`, so check it too.

**8. No CSRF protection (Identification & Authentication Failures / Insecure Design)**
- No anti-CSRF token appears on `invoiceForm`, `paymentForm` or `payment-form`, or in the AJAX calls to `paylib.php`. A state-changing payment submission may be forgeable, depending on SameSite cookie settings.
- Severity: **Medium**.

**9. Inconsistent output encoding (Injection / XSS)**
- `echoLine` interpolates `$iname`, `$date` and `$encounter` (`enc: reason`, where `reason` is free text) into HTML in parts of the function not visible in the diff. Verify these use `text()` or `attr()`.
- The patient panel mixes `htmlspecialchars` and `text`. The change from `attr()` to `text()` for the card fields is correct, but the card-number echo was missed.
- Severity: **Low–Medium**.

## Low

**10. Third-party scripts without integrity pinning and verbose errors (Software & Data Integrity Failures / Logging)**
- Stripe and Authorize.Net `Accept.js` are used on a payment page. Their include tags are not in the diff, so check they are loaded from official HTTPS URLs.
- Gateway and server error text is shown with `alert(data)` and logged with `console.log`. This can leak internal details.
- Payment posting and audit-record viewing have no explicit security logging. In particular, there is no log of staff viewing full card data.
- Severity: **Low**.

**11. Client-side-only card validation**
- The `pattern="\d"` and Luhn checks are cosmetic. Server-side validation of all card fields is required.
- Severity: **Low**.

## Priority fixes
1. Stop emitting `gateway_api_key` to the client, and rotate the Stripe secret if this code has been deployed.
2. Bind `pid` and `recid` to the session for portal users.
3. Require a staff session and ACL for the `form_save` block.
4. Escape the card number output, and stop storing or displaying the CVV and full PAN.
5. Add CSRF tokens and server-side amount validation.