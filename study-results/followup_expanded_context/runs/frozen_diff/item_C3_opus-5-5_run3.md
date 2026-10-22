# Code Review: `portal/portal_payment.php`

This PR adds Authorize.Net and Stripe tokenized payments, `recid` audit-record lookup, column totals, `sequence_no` handling, and a lot of reformatting. The reformatting makes the real changes hard to find. I'd ask that formatting be split into its own commit. Findings are grouped by severity.

---

## Critical / High

### 1. Patient can read other patients' audit and card data (`$recid`)
- **Location:** `$recid = (int) $_REQUEST['recid']` → `getPortalAuditRec($recid)`.
- **Problem:** Any portal session can pass an arbitrary `recid`. Nothing checks that the record belongs to the session patient (`$_SESSION['pid']`).
- **Impact:** The record's `checksum` is decrypted into `$ccdata` and rendered: card number, expiry, CVV, name and zip.
- **Fix:** When `$isPortal` is true, verify that `$edata['patient_id']` matches `$_SESSION['pid']`, or ignore `recid` entirely. The new `$isPortal` flag is set but never used for this.

### 2. `$pid` can be overridden from the request in portal context (pre-existing, but this PR widens exposure)
- **Location:** `$pid = isset($_REQUEST['pid']) ? ... ; $pid = $_REQUEST['hidden_patient_code'] > 0 ? ...`
- **Problem:** A portal patient can view another patient's demographics, encounters and balances. This now also includes `postal_code`, which is pre-filled into the form.
- **Fix:** When `$isPortal`, force `$pid = $_SESSION['pid']`.

### 3. Portal patients can post payments directly (pre-existing, unaddressed)
- **Location:** The `if ($_POST['form_save'])` block.
- **Problem:** There is no check that the caller is staff (`$_SESSION['authUserID']`). A portal patient can POST `form_save=1&form_upay[enc]=500&radio_type_of_payment=invoice_balance` straight to this page. That inserts `ar_session`, `ar_activity` and `payments` rows, with no card being charged.
- **Related:** `form_pid` is also taken from POST unchecked.
- **Fix:** Require `$_SESSION['authUserID']` (and an ACL check) before processing saves. Ignore `form_pid` for portal users.

### 4. Gateway secret possibly leaked to every page
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Problem:** The key is emitted unconditionally, for every gateway, to every portal user. For Authorize.Net the API Login ID is acceptable client-side. For Stripe (or if an admin stores the transaction key or secret key in this global), it exposes a live secret.
- **Fix:** Emit only what each gateway's client library needs (publishable key / clientKey + loginID), and only for the active gateway. Never send `sk_*` or transaction keys.

### 5. Raw card data and CVV still stored and displayed (PCI-DSS)
- **InHouse path:** Full PAN and CVV are still sent to `paylib.php` and stored (encrypted) in the audit record.
- **Display:** The CVV is rendered back to the page (`text($ccdata["cardCode"])`), including to the patient. The full card number is shown to staff, and to the patient whenever `transId` is set.
- **Why it matters:** Storing the CVV after authorization is prohibited outright, regardless of encryption.
- **Fix:**
  - Drop CVV storage and display.
  - Mask the PAN everywhere.
  - Consider deprecating InHouse capture now that tokenized gateways exist.

### 6. Gateway JS libraries never loaded
- **Location:** The AuthorizeNet and Stripe blocks.
- **Problem:** `Accept.dispatchData(...)` and `Stripe(publicKey)` are called, but no `<script src="https://js.authorize.net/v1/Accept.js">` or `https://js.stripe.com/v3/` tag is added. The comment says "Include Authorize.Net dependency" but nothing is included.
- **Impact:** Unless these are injected elsewhere, both gateways throw `ReferenceError`. The Stripe one runs at top level, so the rest of that script block breaks too.

---

## Medium

### 7. Transactions don't prevent duplicate `sequence_no`
- **Location:** Each `sqlBeginTrans(); SELECT IFNULL(MAX(sequence_no),0)+1 ...; INSERT ...; sqlCommitTrans();` block.
- **Problem:** A plain `SELECT MAX()` inside a transaction takes no lock, so two concurrent postings can compute the same value.
- **Fix:** Use `SELECT ... FOR UPDATE`, or rely on a unique key plus retry.
- **Atomicity:** The surrounding `ar_session` insert and `frontPayment()` are outside the transaction, so a failure leaves partial financial records. Wrap the whole posting per encounter in one transaction.

### 8. Copay no longer creates or attaches an encounter
- **Location:** The `calendar_arrived($form_pid)` call was removed.
- **Problem:** For copay with `$enc == 0`, the copay is now posted against encounter `0`, creating orphan `ar_activity` and `payments` rows.
- **Fix:** If removal is intentional (copay is hidden for portal users), reject `enc == 0` for copay instead of silently posting.

### 9. Inconsistent and possibly null `post_user` / `user_id`
- **Problem:** The copay path uses `$_SESSION['authId']`, while the invoice-balance path uses `$_SESSION['authUserID']`. Previously these were hardcoded `3`.
- **Impact:** In portal or onsite contexts either may be unset, giving NULL or 0 users and lost audit attribution.
- **Fix:** Pick one and define a fallback.

### 10. Payment amount is client-controlled
- **Location:** `paymentAmount` is filled from `form_paytotal` on modal show and sent to `paylib.php`.
- **Fix:** The server must recompute the amount from `invValues` and outstanding balances, and reject amounts ≤ 0.
- **Related:** `sendPaymentDataToAnet` does no client-side amount check either.

### 11. Authorize.Net errors are swallowed
- **Location:** `acceptResponseHandler`.
- **Problem:** On `resultCode === "Error"`, messages go only to `console.log`. The user clicks "Pay Now" and nothing visible happens.
- **Fix:** Surface the errors in the UI.

### 12. Totals are computed from formatted strings
- **Problem:** `$balance = bucks(...)` returns a formatted string, which is then summed with `$sum_balance += $balance * 1`. If `bucks()` ever adds thousands separators, `"1,234.00" * 1 === 1`.
- **Fix:** Sum the raw numeric value.
- **Sign check:** `$sum_ptpaid` and `$sum_inspaid` are multiplied by `-1`. Verify the totals row shows the same sign as the per-row cells.

### 13. Totals cells may be hidden by the existing JS
- **Problem:** `td_total_1..8` previously held blanks and are shown/hidden by `make_it_hide_*` and `make_visible*`. They now hold values and have shifted one column, so the hide/show logic may mis-align or hide the wrong totals.

### 14. InHouse `#paySubmit` handler is likely never bound
- **Problem:** `$('#paySubmit').click(...)` runs in `<head>` before the button exists. It is not wrapped in `$(function(){...})`.
- **Related:** `extra` concatenates raw JSON into a urlencoded body without `encodeURIComponent`, so any `&`, `+` or `#` in values corrupts the payload.

---

## Low / Maintainability

- **Duplicate element IDs:** `id='mode'` appears in both `invoiceForm` and `paymentForm`, so `$("#mode").val(...)` hits whichever comes first. `id='pid'`, `payTotal` and `paymentAmount` are also fragile.
- **Copy-paste bug:** `text($ccdata["transId"]) . "/" . text($ccdata["year"])` appends the expiry year to the transaction ID. The span also reuses `id="ed"`.
- **Malformed HTML:** `echo '...<tr">'` has a stray quote. The PHP indentation in these blocks is also broken.
- **Ineffective `pattern` attributes:** `pattern="\d"` on card number and zip only matches a single digit. They have no effect anyway, since submission goes via `fetch`. `required` attributes were also removed.
- **Hardcoded expiry years (2019–2028):** These will go stale. Generate them from the current year.
- **Stripe retries:** Each attempt appends another hidden `stripeToken` input to the form.
- **Redundant filter logic:** `option_id != 'credit_card' || option_id == 'debit' || option_id == 'bank_draft'`. The OR terms are dead; the condition is just `!= 'credit_card'`.
- **Wrong escaping in `getAuth`:** `xlt()` is used inside a JS string literal. Use `xlj`/`js_escape`, since HTML entities will display literally. Also fix the typo "comfirmation".
- **Unused variable:** `$isPortal` is introduced but never used. Either use it for the authorization checks above or remove it.
- **jQuery path change:** The receipt page now uses `/jquery/dist/jquery.min.js`. Confirm the asset exists in all supported installs.