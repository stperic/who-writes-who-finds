# PR Review: `portal/portal_payment.php`

## Critical / Security

### 1. Gateway secret key exposed to the browser
- **Location:** JS block, `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Problem:** `globals.inc.php` describes `gateway_api_key` as *"Auth Name for Authorize.Net and API Secret for Stripe."* The value is echoed into every page render, for every gateway (InHouse and Stripe included).
  - With Stripe selected, the **Stripe secret key** reaches any portal patient's browser. Anyone holding it can issue charges and refunds against the merchant account.
  - Only the Authorize.Net branch needs `apiLoginID`, and only `clientKey`/`apiLoginID` should ever go to the client.
- **Fix:** Emit `apiKey` only in the AuthorizeNet branch, and never emit it for Stripe.
- **Related:** These settings are type `encrypted`. Confirm they are decrypted before use. If they are not, the gateway receives ciphertext and fails.
- **Severity:** Critical

### 2. Unauthorized access to payment audit records (`recid`)
- **Location:** `$recid = (int)$_REQUEST['recid']` → `getPortalAuditRec($recid)`
- **Problem:** Any caller can pass an arbitrary `recid`, including a portal patient. Nothing checks that the record belongs to the session `pid`, and the `$isPortal` flag added in this PR is never used to enforce that.
  - A patient can therefore enumerate other patients' payment records.
  - Those records contain decrypted card data: name, number, expiry, CVV, zip, and charge amount.
- **Fix:** Restrict `recid` to authenticated staff, or verify that the record's `pid` matches the session pid when `$isPortal` is true.
- **Related:** The pre-existing `$pid = $_REQUEST['pid'] / hidden_patient_code` overrides should likewise be ignored when `$isPortal`.
- **Severity:** Critical

### 3. Full card number shown to the patient, without escaping
- **Location:** `if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) { echo $ccdata["cardNumber"] ...`
- **Problem:** Once `transId` is set, the unmasked PAN is shown to non-staff users. Combined with #2, this exposes other patients' card numbers.
- **Problem:** The value is echoed raw (no `text()`), so it is also a stored-XSS vector.
- **Fix:** Always mask the PAN unless staff, and escape the output.
- **Severity:** Critical / High

### 4. CVV (`cardCode`) is still stored and displayed
- **Location:** `<span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?>`, InHouse flow
- **Problem:** Storing the CVV after authorization is prohibited by PCI DSS. This is pre-existing, but the PR renames and continues it.
- **Fix:** At minimum, flag this behavior. Ideally, drop CVV persistence entirely.
- **Severity:** High

## Correctness

### 5. Stripe.js and Accept.js are never loaded
- **Location:** The AuthorizeNet and Stripe script blocks
- **Problem:** `Stripe(publicKey)` and `Accept.dispatchData(...)` are called, but no `<script src="https://js.stripe.com/v3/">` or Accept.js include is added. The comment even says "Include Authorize.Net dependency," but no include follows.
- **Effect:** Both gateways throw `ReferenceError`. On Stripe, the error occurs at page load and breaks the whole script block.
- **Severity:** High

### 6. Removed `calendar_arrived()` fallback for copay
- **Location:** The `form_upay` loop
- **Problem:** The block that set `$enc = calendar_arrived($form_pid)` when `$enc` is 0 for non-`invoice_balance` payments was deleted.
- **Effect:** Copay or cash payments against encounter 0 are now posted to `ar_activity` with `encounter = 0`, and `form_encounter`/`billing` updates are made for encounter 0.
- **Also:** `$zero_enc` is now dead code.
- **Severity:** High

### 7. Sequence-number "transactions" do not prevent races and never roll back
- **Location:** Every `sqlBeginTrans(); SELECT IFNULL(MAX(sequence_no),0)+1 ...; INSERT ...; sqlCommitTrans();`
- **Problem:** A plain `SELECT MAX` inside a transaction takes no lock. Concurrent posts can still compute the same `sequence_no`; `SELECT ... FOR UPDATE` is needed.
- **Problem:** There is no rollback on failure.
- **Problem:** The related `ar_session` insert and the `frontPayment()` call sit outside the transaction, so partial postings remain possible.
- **Severity:** Medium

### 8. Inconsistent `post_user` / `user_id` sources
- **Copay path:** uses `$_SESSION['authId']` for both `ar_session.user_id` and `ar_activity.post_user`.
- **Invoice path:** uses `$_SESSION['authUserID']`.
- **Before this PR:** the value was the constant `3`.
- **Effect:** In the portal context (`$ignoreAuth`), these session keys may be unset, producing NULL or empty users.
- **Severity:** Medium

### 9. Totals row arithmetic is wrong
- **Location:** `echoLine()` accumulators
- **Sign error:** `$sum_ptpaid += $ptpaid * -1` and `$sum_inspaid += $inspaid * -1` negate values that are positive per row (balance = charges − ptpaid − inspaid). The totals will display with the opposite sign from the rows.
- **Formatting error:** `$balance` has already been passed through `bucks()`, which is a formatted string (possibly with thousands separators, e.g. `"1,234.00"`). `$balance * 1` then truncates or warns, so `$sum_balance` is wrong for amounts ≥ 1000.
- **Fix:** Accumulate the raw numeric value.
- **Severity:** Medium

### 10. Copy-paste bug in transaction display
- **Location:** `text($ccdata["transId"]) . "/" . text($ccdata["year"])`
- **Problem:** The card's expiry year is appended to the Transaction ID.
- **Problem:** The `ed` and `cvvpin` ids are reused for unrelated content.
- **Severity:** Low

### 11. Malformed HTML
- **Location:** `echo '<tr height="5"><td colspan="3"></td></tr><tr">';`
- **Problem:** `<tr">` has a stray quote.
- **Severity:** Low

### 12. Duplicate element IDs
- **Problem:** `id='mode'` appears in both `invoiceForm` and `paymentForm`, and the code calls `$("#mode").val(...)`. Which element gets set depends on DOM order.
- **Fix:** Use form-scoped selectors.
- **Severity:** Low

### 13. `#paySubmit` handler likely never binds
- **Problem:** The button now lives in the modal footer, outside `paymentForm`. The `click` binding runs in a `<head>` script before the element exists, and nothing wraps it in `$(function(){...})`.
- **Effect:** For InHouse, the button likely does nothing.
- **Severity:** Medium

### 14. Silent failure in the Authorize.Net flow
- **Location:** `acceptResponseHandler`
- **Problem:** Errors only go to `console.log`. The user gets no feedback when card tokenization fails.
- **Severity:** Low / Medium

### 15. Stripe token inputs accumulate
- **Location:** `stripeTokenHandler`
- **Problem:** A new hidden `stripeToken` input is appended on every click, and the submit button is not disabled during the request.
- **Effect:** Double submission can cause a double charge.
- **Severity:** Medium

### 16. Validation regressions on card fields
- **Problem:** `required` was removed from the card fields.
- **Problem:** The zip field has `pattern="\d"`, which matches a single digit only.
- **Problem:** The `cardNumber` field keeps its pattern `"\d"`.
- **Severity:** Low

## Maintainability

- **Dead/confusing payment-method filter:** `$brow1112['option_id'] != 'credit_card' || ... == 'debit' || ... == 'bank_draft'`. The second and third terms can never matter.
- **Hard-coded expiry years:** The year list (2019–2028) will go stale. Generate it from the current year.
- **Unguarded array access:** `$ccdata['authCode']`, `$ccdata['transId']`, and similar keys are read without `isset`, producing notices when there is no audit record.
- **Duplicated code:** The Stripe and Authorize.Net `fetch` submit and response handling is copy-pasted. Extract a shared helper.
- **Unused variable:** The `$isPortal` flag is introduced but never used. Use it for the authorization checks in #2.