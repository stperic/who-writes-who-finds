# Review of `portal/portal_payment.php`

## Critical / High

**1. Stripe secret key exposed to the browser (Critical, security)**
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Problem:** `globals.inc.php` describes `gateway_api_key` as *"Auth Name for Authorize.Net and API Secret for Stripe"*. This line is emitted on every render of the page, for every gateway, including to portal patients.
- **Impact:** With Stripe configured, the account's secret key is published to every patient. Anyone holding it can issue refunds, read customer data, and create charges.
- **Fix:** Only emit the public key. Emit the API login ID only when `payment_gateway == 'AuthorizeNet'`. Never emit the Stripe secret.
- **Also check:** both globals have type `'encrypted'`. Confirm they are decrypted before use, otherwise ciphertext is being sent and tokenization will fail.

**2. IDOR via `recid` exposes other patients' payment and card data (High, security)**
- **Location:** `$recid = (int)$_REQUEST['recid']` → `getPortalAuditRec($recid)`
- **Problem:** The record is fetched by ID with no check that it belongs to the session patient.
- **Impact:** A logged-in portal patient can enumerate `recid` and see other patients' decrypted card data, including name, zip, card number, expiry and CVV. The full card number is shown whenever `transId` is set.
- **Fix:** For portal sessions, verify that `$edata['patient_id'] == $_SESSION['pid']`. In the same spirit, portal users should not be able to override `$pid` from `$_REQUEST['pid']` or `hidden_patient_code` (pre-existing, but now more dangerous).

**3. Card data handling / PCI (High, security)**
- Raw card number, expiry and CVV are still stored (encrypted) in the audit record and displayed to staff for the InHouse gateway. Storing CVV is prohibited by PCI DSS.
- `echo $ccdata["cardNumber"]` is output unescaped. This field is patient-supplied, so it is stored XSS against staff viewing the record. Use `text()`.

**4. Stripe.js and Accept.js are never loaded (High, correctness)**
- **Problem:** The code calls `Stripe(publicKey)` and `Accept.dispatchData(...)`, but no `<script src="https://js.stripe.com/v3/">` or Accept.js include exists.
- The comment *"Include Authorize.Net dependency to tokenize card"* is not followed by any include.
- **Impact:** Both gateways throw a `ReferenceError` and are completely non-functional.

**5. `sequence_no` generation is not race-safe (High, data integrity)**
- **Location:** the `sqlBeginTrans(); SELECT IFNULL(MAX(sequence_no),0)+1 ...; INSERT ...; sqlCommitTrans();` blocks.
- **Problem:** A plain `SELECT MAX` inside a transaction takes no lock. Concurrent postings for the same pid/encounter can compute the same sequence number, causing duplicate-key failures or duplicate sequences.
- **Fix:** Use `SELECT ... FOR UPDATE`, or reuse the existing helper used elsewhere in OpenEMR billing code.
- **Also:**
  - There is no rollback path on failure.
  - The related `ar_session` insert and the `frontPayment()` call sit outside the transaction, so partial postings are possible.

## Medium

**6. Inconsistent `post_user` / `user_id` sources**
- The copay path uses `$_SESSION['authId']`, while the other paths use `$_SESSION['authUserID']`. Both replaced the previous hard-coded `3`.
- In a portal session `authUserID` is unset, which writes NULL. Pick one source and handle the portal context explicitly.

**7. Encounter 0 no longer resolved for copay**
- **Location:** the copay branch of the `form_upay` loop.
- **Problem:** The `calendar_arrived($form_pid)` fallback for `$enc == 0` was removed.
- **Impact:** A copay posted against `form_upay[0]` now writes `ar_activity` rows with `encounter = 0`.

**8. Total row calculations are wrong**
- `$sum_ptpaid += $ptpaid * -1` and `$sum_inspaid += $inspaid * -1` invert the sign relative to the per-line values, so the totals will not match the column contents.
- `$balance` is the output of `bucks()`, a formatted string. With a thousands separator, `"1,234.00" * 1` evaluates to `1`, so `$sum_balance` is wrong. Accumulate the raw numeric value instead.

**9. AuthorizeNet error path is silent**
- In `acceptResponseHandler`, errors are only written to `console.log`.
- The user gets no feedback, and the card fields stay populated.

**10. Duplicate element IDs**
- The modal form adds `id='mode'` and `id='pid'` while the invoice form already has `#mode`.
- As a result, `$("#mode").val(...)` and `document.forms[...]` lookups become ambiguous.

**11. `#paySubmit` handler is likely never bound (InHouse)**
- `$('#paySubmit').click(...)` runs in a `<head>` script before the button exists, and is not wrapped in `$(function(){...})`.
- The button has also moved to the modal footer, outside any form. The InHouse submit path appears dead.

**12. Client-side validation weakened**
- `required` was removed from the card fields.
- The new zip field has `pattern="\d"`, which matches a single digit only.
- Submission goes through `fetch`/AJAX, so HTML validation is bypassed anyway. The server must validate.

**13. Copay option only hidden in the UI**
- The copay radio is hidden with a CSS class for portal users but is still submitted and accepted.
- Enforce the allowed payment types server-side.

## Low / Maintainability

**14. Transaction Id display bug**
- `text($ccdata["transId"]) . "/" . text($ccdata["year"])` is a copy-paste error.
- It also reuses the `id="ed"` and `id="cvvpin"` IDs from the other branch.

**15. Malformed HTML**
- `echo '<tr height="5"><td colspan="3"></td></tr><tr">';` contains a stray quote in `<tr">`.
- The receipt output also starts with `<htlm>` (pre-existing).

**16. Dead filter conditions**
- In the payment method loop, `if ($id != 'credit_card' || $id == 'debit' || $id == 'bank_draft') continue;` is equivalent to `$id != 'credit_card'`. The extra clauses (just changed from `electronic` to `debit`) do nothing.

**17. Unused variable**
- `$isPortal` is set but never used.

**18. Hard-coded expiry years**
- The 2019–2028 list will go stale. Generate it from the current year.

**19. Wrong escaping for JS context**
- `xlt()` (HTML escaping) is used inside the JS `prompt()` string literal in `getAuth()`. Use `xlj()`/`json_encode`.

**20. Formatting-heavy diff**
- Mixed indentation (`}` at column 0 inside templates) and very large reformatting churn make the functional changes hard to review. Split reformatting from logic changes.