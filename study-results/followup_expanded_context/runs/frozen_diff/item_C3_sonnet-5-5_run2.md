**Issues found in `portal/portal_payment.php`**

**High**

1. **Insecure direct object reference through `recid` (about line 57 and lines 70-80).**
   - `$recid` comes straight from `$_REQUEST`. It is passed to `getPortalAuditRec($recid)` with no check that the audit record belongs to `$pid` or to the logged-in portal patient.
   - A portal user can enumerate `recid` values and load another patient's decrypted card data (`decryptStandard($edata['checksum'])`) and invoice data.
   - `$pid` can also be overridden by `$_REQUEST['pid']` and `hidden_patient_code`, even in portal mode. That is old behaviour, but this PR adds more sensitive data behind it.
   - `$isPortal` is added but never used. For portal sessions, force `$pid` to the session value and require `$edata['pid'] == $pid`.

2. **Possible gateway secret leaked to the browser (about lines 570-580).**
   - `var apiKey = json_encode($GLOBALS['gateway_api_key'])` is emitted for every gateway, including Stripe.
   - For Stripe, the API key is the secret key. Only the publishable key should reach the client.
   - Even for Authorize.Net, emit the key only when that gateway is active.

3. **Full card number can be shown to a non-staff user (about lines 1260-1270).**
   - The condition `isset($_SESSION['authUserID']) || isset($ccdata["transId"])` prints the full `cardNumber` to a portal patient whenever a `transId` exists in the record.
   - Combined with issue 1, this exposes full PANs.
   - The page also still stores and displays full PAN and CVV from the "in house" path. That is a PCI problem, though it is a design decision that predates this PR.
   - Mask the number unless the viewer is staff.

4. **Unescaped output of card data (about line 1265).**
   - `echo $ccdata["cardNumber"]` is not escaped, while the other fields were switched to `text()`. Use `text()` here too.

**Medium**

5. **No authorization guard on the save path.**
   - The `form_save` block (inserts into `ar_session` and `ar_activity`, `cash` handling that marks encounters billed) is reachable by a portal session posting directly.
   - A portal user could record payments or close encounters without any gateway involvement.
   - `$isPortal` should gate this block.
   - For portal users, `$_SESSION['authUserID']` is unset, so `post_user` and `user_id` become NULL or 0.

6. **Payment amount is client-supplied.**
   - `#paymentAmount` is filled from `form_paytotal` in JS and posted to `paylib.php`.
   - `paylib.php` is not in this diff. Confirm it recomputes the amount server-side from the invoice.

7. **Race in `sequence_no` allocation (copay and invoice inserts).**
   - `sqlBeginTrans()` followed by `SELECT MAX(sequence_no)+1` without `FOR UPDATE` does not prevent concurrent duplicates.
   - There is no rollback on error.
   - The same block is copy-pasted three times. Extract a helper.

8. **Silent failures in Authorize.Net tokenization.**
   - `acceptResponseHandler` only `console.log`s errors, so the user gets no feedback.
   - Client-side validation was weakened: `required` was removed from the inputs, and `pattern="\d"` on the card number and zip only matches a single digit.
   - Make validation consistent and fix the patterns, for example `\d{5}` for zip.

9. **Behaviour change: encounter fallback removed.**
   - The `calendar_arrived($form_pid)` fallback for `!$enc` was deleted.
   - If `$enc` is 0 or empty, inserts now go to encounter 0. Confirm this is intended.

10. **Third-party scripts for Stripe and Authorize.Net are not loaded here.**
    - `Stripe(...)` and `Accept.dispatchData` are used, but their script includes are not in this diff. If they are not loaded elsewhere, both gateways will throw.

**Low**

11. **Malformed HTML.** `'<tr height="5">...</tr><tr">'` contains a stray quote.
12. **Hard-coded expiry-year list (2019-2028).** It will go stale. Generate it from `date('Y')`.
13. **Duplicate element IDs and names.** `mode`, `cc_type`, `payment` and `cardHolderName` appear in multiple forms. `$("#mode")` only hits the first one, so this is fragile.
14. **Inconsistent session keys.** The copay path uses `$_SESSION['authId']` while the others use `authUserID`.
15. **Undefined index notices.** `$ccdata['authCode']`, `$ccdata['transId']` and `$payrow['source']` may be undefined.
16. **Redundant method filter.** The `payment_method` condition is `!= 'credit_card' || == 'debit' || ...`, which is equivalent to `!= 'credit_card'`. Swapping `electronic` for `debit` has no effect.
17. **Missing semicolon.** `var ccerr = <?php ... ?>` has no `;`. It works through ASI but is fragile.
18. **Mixed concerns.** Large whitespace and format-only churn is mixed with functional changes, which makes review harder.