# Code Review: `portal/portal_payment.php`

## Critical

**1. IDOR via `recid`: any patient can read other patients' decrypted card data**
- **Location:** `$recid = (int) $_REQUEST['recid']` → `getPortalAuditRec($recid)`
- **Problem:** The record is fetched by ID only. Nothing checks that it belongs to `$pid` or to the logged-in portal patient. The result is decrypted (`decryptStandard($edata['checksum'])`) and rendered: card number, expiry, CVV, name and zip.
- **Context:** `$isPortal` is set but never used to restrict anything. The existing `$_REQUEST['pid']` / `hidden_patient_code` overrides have the same flaw. A portal user can pass another patient's `pid` and see their invoices or post against them.
- **Fix:** For portal sessions, force `$pid = $_SESSION['pid']`. Ignore request-supplied `pid` and `hidden_patient_code`. Verify `$edata['patient_id'] == $pid` before decrypting.

**2. Possible secret key leak to the browser**
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Problem:** This is emitted for every gateway, to every portal user. Only Authorize.Net's Accept.js needs a public login ID.
- **Risk:** If `gateway_api_key` holds a Stripe secret key or the Authorize.Net transaction key, it is publicly exposed.
- **Fix:** Emit it only when `payment_gateway == 'AuthorizeNet'`. Make sure it is the public login ID, never a transaction or secret key.

**3. Card number rendered unescaped, and in full to patients**
- **Location:** `echo $ccdata["cardNumber"]` inside the `if (isset($_SESSION['authUserID']) || isset($ccdata["transId"]))` branch
- **Problems:**
  - The value is output with no `text()` escaping, so a crafted value is stored XSS.
  - The new `|| isset($ccdata["transId"])` condition shows the full PAN to the patient whenever a transaction ID exists.
- **Related:** CVV (`cardCode`) is still stored (encrypted) and displayed. Retaining CVV after authorization is a PCI-DSS violation.
- **Fix:**
  - Always escape the output.
  - Always mask to the last 4 digits.
  - Stop persisting CVV.

## High

**4. Accept.js and Stripe.js are never loaded**
- **Location:** The AuthorizeNet and Stripe script blocks.
- **Problem:** The comment says "Include Authorize.Net dependency", but no `<script src=...>` tag exists for Accept.js or `https://js.stripe.com/v3/`.
- **Impact:** `Accept.dispatchData` and `Stripe(publicKey)` throw `ReferenceError`. Both new gateways are non-functional.

**5. jQuery handlers bound before their elements exist**
- **Location:** `$('#paySubmit').click(...)`, `$('#openPayModal').on('show.bs.modal', ...)`, `$("#invoiceForm").on('submit', ...)`
- **Problem:** These run in a `<script>` placed before `<body>`, with no `$(document).ready` wrapper (the old empty `$(document).ready();` was removed). The selectors match nothing.
- **Impact:**
  - `#payTotal` and `#paymentAmount` are never populated.
  - InHouse `#paySubmit` does nothing.
  - The staff "Post Payment" submit bypasses the AJAX path.
- **Fix:** Wrap the bindings in `$(function(){...})` or move them to the end of the body.

**6. `post_user` may be NULL or invalid in portal context**
- **Location:** The `ar_activity` inserts.
- **Problem:** `post_user` was a hard-coded `3` and is now `$_SESSION['authId']` (copay) or `$_SESSION['authUserID']` (PP rows). In a portal session these are unset, so you get NULL or empty, which may violate `NOT NULL`.
- **Inconsistency:** `authId` and `authUserID` are mixed between the two inserts.

**7. `sequence_no` computation is not race-safe, and transactions have no rollback**
- **Location:** `sqlBeginTrans(); SELECT IFNULL(MAX(sequence_no),0)+1 ...; INSERT ...; sqlCommitTrans();`
- **Problems:**
  - A plain `SELECT MAX` inside a transaction does not lock under InnoDB REPEATABLE READ. Concurrent posts can compute the same sequence number and collide on the PK, or fail.
  - There is no rollback on error.
  - The `ar_session` and `payments` inserts sit outside the transaction, so partial writes are possible.
- **Fix:** Use `SELECT ... FOR UPDATE`, or the existing core helper used elsewhere for `ar_activity` sequencing. Wrap the whole posting in one transaction with rollback.

**8. Removed `calendar_arrived()` fallback**
- **Location:** The `foreach ($_POST['form_upay'] ...)` loop.
- **Problem:** The "no encounter" handling was deleted. If `$enc` is `0`, rows are now written against encounter 0 instead of today's encounter.
- **Fix:** Confirm no code path can submit `form_upay[0]`. If one can, reject it.

## Medium

**9. Copy-paste bug in Transaction Id display**
- **Location:** `text($ccdata["transId"]) . "/" . text($ccdata["year"])`
- **Problem:** The expiry year is appended to the transaction ID.
- **Also:** `id="ed"` and `id="cvvpin"` are reused for different semantics.

**10. Totals have wrong signs and are likely miscomputed**
- **Location:** The new `$sum_*` accumulation in `echoLine`.
- **Problems:**
  - `$sum_ptpaid += $ptpaid * -1` and `$sum_inspaid += $inspaid * -1` negate values that are displayed as-is per row. Totals won't match the column.
  - `$balance` is the output of `bucks()`. If that is a formatted string (e.g. with thousands separators), `$balance * 1` truncates.
- **Fix:** Accumulate raw numerics before formatting.

**11. Duplicate element IDs across forms**
- **Location:** `id='mode'` in both `invoiceForm` and `paymentForm`.
- **Problem:** `$("#mode")` always hits the first one.
- **Also:** `payTotal`, `paymentAmount`, `invValues` and `cardHolderName` are duplicated in the template branches. This is fragile.

**12. Client-side validation weakened or broken**
- **Problems:**
  - `required` was removed from the card fields.
  - `pattern="\d"` on `cardNumber` and `cczip` only matches a single digit, so it is invalid for any real value. It is only harmless because `fetch` bypasses native validation.
  - The CVV `pattern` was removed.
- **Fix:** Correct the patterns (e.g. `\d{13,19}`, `\d{5}(-\d{4})?`) or drop them.

**13. Authorize.Net errors are invisible to the user**
- **Location:** `acceptResponseHandler`.
- **Problem:** Errors only go to `console.log`, so the patient sees nothing.
- **Fix:** Surface the error message in the UI.

**14. Raw server output shown to the user**
- **Location:** The `fetch` handlers, `alert(data)` when `data !== 'ok'`.
- **Problem:** Raw server output (possibly PHP errors or stack traces) is shown to the patient.

## Low / Maintainability

- **Malformed HTML:** `echo '... <tr">'` has a stray quote. Also note `<htlm>`, which predates this PR.
- **Inconsistent indentation:** In the PHP blocks (e.g. the `$payrow['source']` and `$hide` sections), the closing `}` is at column 0.
- **Redundant condition:** `$brow1112['option_id'] != 'credit_card' || ... == 'debit' || ...` — the trailing clauses are redundant. Only credit_card ever passes. Simplify.
- **Hard-coded expiry years:** 2019–2028 will rot. Generate the list from the current year.
- **Unsafe JSON in `<script>`:** `json_encode` is used without `JSON_HEX_TAG`. A translation containing `</script>` would break out of the script block.
- **Unused variable:** `$isPortal` is set but unused (see issue 1).
- **Default behavior change for staff:** The default radio changed from Co Pay to Invoice Balance for staff as well as for portal users. Confirm this is intended.
- **Mixed JS conventions:** `var`, `let` and `const` are mixed in the same scope, and some semicolons are missing (`let flag = 0`).
- **Large PR:** Much of the diff is pure reformatting mixed with functional changes. Split it into separate commits to make review and blame tractable.