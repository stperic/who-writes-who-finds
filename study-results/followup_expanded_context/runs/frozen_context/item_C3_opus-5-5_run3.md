# PR review: `portal/portal_payment.php`

## Critical

**1. Gateway secret key is sent to every portal user's browser**
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Problem:** `globals.inc.php` describes `gateway_api_key` as "Auth Name for Authorize.Net and **API Secret for Stripe**". With Stripe configured, the account's secret key is embedded in the page for any logged-in patient. Anyone holding it can issue charges and refunds and read customer data.
- **Additional notes:**
  - The Stripe client code only needs `publicKey`.
  - Authorize.Net's Accept.js needs the API login ID, not a secret.
  - The setting is typed `encrypted`, which signals it must never leave the server.
- **Fix:** Emit only the key each gateway actually requires on the client. Never emit the Stripe secret.

**2. IDOR via the new `recid` parameter exposes card data**
- **Location:** `$recid = (int)$_REQUEST['recid']` → `getPortalAuditRec($recid)` → `decryptStandard($edata['checksum'])`
- **Problem:** The record is loaded by ID with no check that it belongs to `$pid` or the session patient. A portal patient can walk `recid` values and see other patients' decrypted payment records: name, zip, card number, expiry and CVV.
- **Related:** `$pid` itself can still be overridden from `$_REQUEST['pid']` / `hidden_patient_code` in a portal session. The new `$isPortal` flag is set but never used to stop this.
- **Fix:**
  - When `$isPortal`, force `$pid = $_SESSION['pid']`.
  - Verify the audit record's `patient_id` matches `$pid`.

## High

**3. Full card number shown to patients**
- **Location:** `if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) echo $ccdata["cardNumber"]`
- **Problem:** The new `transId` condition shows the unmasked card number to the patient, not just staff.
- **Related problems:**
  - CVV is still persisted and rendered (pre-existing), which is a PCI violation.
  - The card number is echoed without `text()`, so it is not escaped.

**4. Stripe and Authorize.Net SDKs are never loaded**
- **Problem:** The code calls `Stripe(publicKey)` and `Accept.dispatchData(...)`, but no `<script>` tag for `js.stripe.com/v3` or Accept.js is added. The comment says "Include Authorize.Net dependency…" but nothing is included.
- **Effect:** Both gateway flows throw a `ReferenceError`. On the Stripe path this happens at page load, which also breaks the rest of that script block.

**5. Event handlers are bound before their elements exist**
- **Location:** The head `<script>` binds:
  - `$('#paySubmit').click(...)`
  - `$('#openPayModal').on('show.bs.modal', ...)`
  - `$("#invoiceForm").on('submit', ...)`
- **Problem:** These run before the body is parsed, and the meaningless `$(document).ready();` was removed. The selectors match nothing.
- **Effect:**
  - The InHouse "Send Payment" button does nothing.
  - `#payTotal` and `#paymentAmount` are never populated, so the Stripe and Authorize.Net payment amount is empty.
  - Staff "Post Payment" falls back to a plain form POST.
- **Fix:** Wrap the bindings in `$(function(){...})`.

**6. Copay can be posted against encounter 0**
- **Problem:** The `calendar_arrived($form_pid)` fallback for `!$enc` was removed. A copay on the `form_upay[0]` line now writes `ar_activity` and `payments` rows with `encounter = 0`, which creates orphan accounting records.

## Medium

**7. `post_user` is NULL for portal-originated postings**
- **Problem:** The value changed from the constant `3` to `$_SESSION['authUserID']` (and `$_SESSION['authId']` on the copay path). In a portal session these are unset, so the inserted `post_user` is NULL. This may also violate the column constraint.

**8. `sequence_no` race condition and transaction handling**
- **Location:** `SELECT IFNULL(MAX(sequence_no),0)+1` inside `sqlBeginTrans()`
- **Problems:**
  - The read takes no lock (no `FOR UPDATE`), so two concurrent postings can get the same sequence number. That causes a duplicate key error or a lost row.
  - There is no rollback on failure.
  - The parent `ar_session` insert sits outside the transaction, so a failure leaves an orphan session row.

**9. Totals are computed from formatted strings**
- **Location:** `$sum_balance += $balance * 1;` where `$balance = bucks(...)`
- **Problem:** `bucks()` returns a formatted string such as `"1,234.00"` (thousands separator and locale decimal point). Multiplying it yields a wrong value (`1`) or a non-numeric warning.
- **Related:** `$sum_ptpaid` and `$sum_inspaid` are negated, so verify their sign matches the per-row display.
- **Fix:** Accumulate from the raw numeric values.

**10. Authorize.Net errors are silent**
- **Location:** `acceptResponseHandler`
- **Problem:** Errors only go to `console.log`. The patient clicks "Pay Now" and gets no feedback.

**11. Duplicate element IDs**
- **Problem:**
  - `id='mode'` exists in both `invoiceForm` and `paymentForm`.
  - `payTotal`, `paymentAmount` and `cardHolderName` are also repeated.
- **Effect:** `$("#mode")` and `getElementById` silently target the first match, which is fragile.

## Low / maintainability

- **Wrong transaction display:** The Transaction Id output appends `"/" . $ccdata["year"]`, which looks like a copy-paste error. It also reuses `id="ed"`.
- **Malformed HTML:** `echo '...<tr">'` has a stray quote.
- **Broken input patterns:** `pattern="\d"` on the zip and card number fields only accepts a single digit. `required` was removed from the card fields.
- **Hard-coded expiry years:** The 2019–2028 list will go stale; generate it from the current year.
- **Redundant filter logic:** In the payment-method filter, `!= 'credit_card' || == 'debit' || == 'bank_draft'` is redundant; only the first clause matters.
- **Raw request reads:** `$_REQUEST['hidden_patient_code'] > 0` and the other `$_REQUEST` / `$_POST` reads have no `isset` checks, which produces notices.
- **Inconsistent escaping:** The file mixes `htmlspecialchars` and `attr()`/`text()`, and uses `xlt()` inside an attribute (`value='<?php echo xlt('Invoice') ?>'` should use `xla`).