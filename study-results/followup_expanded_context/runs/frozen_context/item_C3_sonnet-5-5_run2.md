I found two security problems that should block the merge, a few correctness problems, and some smaller maintainability issues.

**Critical / High**

1. **Gateway secret exposed to the browser** (`var publicKey = …; var apiKey = json_encode($GLOBALS['gateway_api_key'])`)
   - The global is described as "Auth Name for Authorize.Net and API Secret for Stripe". For Stripe it is the secret key, and it is printed into the page JS for every portal user. This is written out whatever gateway is selected.
   - Only the publishable key and, for Authorize.Net, the API login ID belong client-side. Emit them only for the gateway that needs them, and never emit the Stripe secret.

2. **IDOR on the new `recid` parameter** (`$edata = $appsql->getPortalAuditRec($recid)`)
   - `recid` comes straight from `$_REQUEST` and loads an audit record with no check that it belongs to `$pid` or to the logged-in portal patient.
   - The record is decrypted and rendered with card holder name, zip, transaction ID, auth code, charge total and card number. Where `transId` is set, the full `cardNumber` is shown.
   - `$pid` can also be overridden from `$_REQUEST['pid']` and `hidden_patient_code`, so a portal user can read other patients' payment data.
   - Ignore `recid` when `$isPortal` is true, or verify record ownership. `$isPortal` is set in this diff but never used.

3. **Stored XSS and unescaped output** (`echo $ccdata["cardNumber"]` and `substr($ccdata["cardNumber"], -4)`)
   - The card number is patient-submitted data, stored and later shown to staff, and it is echoed unescaped. Use `text()`.
   - The other fields were moved from `attr()` to `text()`, which is correct, but this one was missed.

4. **Card data and CVV are still stored and displayed**
   - In the InHouse gateway the full PAN and CVV (`cardCode`) are stored, even if encrypted, and shown to staff. That is a PCI-DSS problem.
   - Removing the CVV display and storage should be a requirement, not an option.

**Medium**

5. **Sequence-number race** (`SELECT IFNULL(MAX(sequence_no),0)+1 … ; INSERT`)
   - `sqlBeginTrans()` is used without `FOR UPDATE` or a lock, so concurrent postings can allocate the same `sequence_no`.
   - The same block is copied three times. Extract a helper.

6. **Inconsistent or possibly null user IDs**
   - `ar_session.user_id` uses `$_SESSION['authId']` for copay but `authUserID` elsewhere. `post_user` now uses `authUserID`, which is likely unset in a portal session, so it will be NULL.
   - Previously the hardcoded `'3'` was passed. Confirm the intended value.

7. **Removed `calendar_arrived($form_pid)` fallback for `$enc == 0`**
   - Copay or other payments with no encounter now pass `enc=0` into the billing lookups and inserts. This behaviour change is unexplained.

8. **Missing third-party scripts**
   - `Stripe(publicKey)` and `Accept.dispatchData` are used, but no `<script>` includes for Stripe.js or Accept.js appear in the diff. If they are not loaded elsewhere, both gateways will throw.

9. **Poor error handling in the Authorize.Net flow**
   - On `resultCode === "Error"` the error is only written to `console.log`, so the user gets no feedback.
   - The modal also loses its close button.

10. **Weakened client-side validation**
    - `required` was dropped from the card inputs.
    - `pattern="\d"` on the card number and zip matches only a single digit. It should be something like `\d+` or `\d{5}`.
    - `beforeSend` only checks the card fields for the InHouse flow.

**Low / Maintainability**

11. **Malformed HTML:** `echo '<tr height="5">…</tr><tr">'` has a stray quote in `<tr">`.

12. **Hardcoded expiry years (2019–2028)** will go stale. Generate them from `date('Y')`.

13. **Duplicate element IDs:** `mode`, `cc_type`, `payTotal`, `paymentAmount`, `invValues` and `cardHolderName` appear in several forms. `$("#mode")` only hits the first one. Use unique IDs.

14. **Dead or confusing conditions**
    - `option_id != 'credit_card' || == 'debit' || == 'bank_draft'` reduces to `!= 'credit_card'`.
    - The "Transaction Id" display prints `transId . "/" . year`, which looks wrong.

15. **Noisy diff:** large reformatting is mixed with functional changes (comment stripping, array reflow, the Copyright year), which makes the security-relevant changes hard to review.