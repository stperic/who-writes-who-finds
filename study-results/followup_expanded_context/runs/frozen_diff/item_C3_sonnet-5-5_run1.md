I found a few serious problems, mostly around the new `recid` lookup and how payment-gateway data is exposed.

**High severity**

1. **Possible IDOR on `recid`** (`portal_payment.php`, `$recid` / `getPortalAuditRec($recid)`)
   - Any portal session can pass `?recid=N`. The code then loads that audit record and decrypts its card data without checking the record belongs to `$pid` or the session patient.
   - `$isPortal` is set but never used for an authorization check.
   - `$pid` can already be overridden by `$_REQUEST['pid']` and `hidden_patient_code`. That was already a problem, but it is much worse now that the page shows decrypted card details.
   - Fix: take `$pid` only from the session for portal users, and require that the audit record's pid matches it.

2. **Gateway API key leaked to the browser** (`var apiKey = json_encode($GLOBALS['gateway_api_key'])`)
   - This is emitted for every gateway, including Stripe and InHouse, where the key may be a secret key.
   - Only emit the public key, and only the login ID for AuthorizeNet, and only when that gateway is active.

3. **Full card number and CVV shown, and output not escaped** (card info panel)
   - `echo $ccdata["cardNumber"]` is not escaped, so it is an XSS risk. The data comes from user-submitted JSON.
   - The full PAN is shown whenever `authUserID` is set or `transId` exists. A tokenized or charged payment should not reveal the full number, and the `transId` condition also exposes it to the patient.
   - CVV (`cardCode`) is displayed, and the InHouse flow stores it. Storing it after authorization violates PCI rules.
   - Fix: escape with `text()`, always mask to the last four digits, and never store or show the CVV.

**Medium severity**

4. **Missing client libraries**
   - The code calls `Accept.dispatchData` (Authorize.Net) and `Stripe(publicKey)`, but this diff loads neither script.
   - The comment says "Include Authorize.Net dependency", yet no include is present.
   - If they are not loaded elsewhere, both gateways fail with a `ReferenceError`.

5. **No user feedback on Authorize.Net errors** (`acceptResponseHandler`)
   - Errors are only logged to the console.
   - The user gets no message and the modal stays in an unclear state.

6. **Client-supplied amount** (`payment`, `invValues`, `form_paytotal`)
   - These are posted to `paylib.php` from the client.
   - Confirm the server recomputes or validates the amounts against the invoice. I can't see that code in this diff.

7. **Behaviour change: `calendar_arrived()` removed**
   - The fallback `if (!$enc) $enc = calendar_arrived($form_pid)` is gone with no explanation.
   - Payments with `enc = 0` now write ar_activity rows against encounter 0.

8. **Inconsistent user IDs**
   - The copay path uses `$_SESSION['authId']` for both `ar_session.user_id` and `post_user`.
   - The other paths use `authUserID`. In a portal context one of these may be unset.
   - The old code hardcoded `'3'`; the new code is arguably better, but it should be consistent.

9. **Transaction handling gives no real protection**
   - `sqlBeginTrans()` is followed by `SELECT MAX(sequence_no)+1` without `FOR UPDATE`, so concurrent posts can still collide.
   - There is no rollback on failure.
   - Transactions are opened and committed repeatedly inside the loop.

**Low severity**

10. **Hardcoded expiry years** (2019–2028): the list will go stale.

11. **`pattern="\d"` on `cardNumber` and `zip`**: this matches a single digit only. It is wrong, and it will break any native form validation.

12. **Display bug**: `text($ccdata["transId"]) . "/" . text($ccdata["year"])` appends the card expiry year to the transaction ID. This looks like a copy-paste error.

13. **Typo in markup**: `echo '<tr height="5">...<tr">'` has a stray quote, which produces malformed HTML.

14. **Duplicate element IDs**
    - `mode`, `cc_type`, `paymentAmount` and `invValues` appear in multiple forms.
    - `$("#mode").val(...)` only touches the first match, so the payment form's `mode` stays empty.

15. **Undefined `$payrow`**: `$payrow['source']` is read and written in the non-receipt branch, where `$payrow` is undefined. This causes a PHP notice.

16. **Dead or odd logic**
    - The payment-method filter `!= 'credit_card' || == 'debit' || ...` is redundant.
    - The modal's close button was commented out, so the only way to dismiss it is Cancel.

17. **Maintainability**
    - The diff mixes large reformatting (SQL calls, comments) with functional changes, which makes review hard.
    - The new jquery asset path (`/jquery/dist/jquery.min.js`) should be verified to exist.