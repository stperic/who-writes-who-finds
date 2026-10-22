# Security Review – `portal/portal_payment.php`

## Critical

### 1. Insecure Direct Object Reference via new `recid` parameter
**Location:** 
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
...
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
} else {
    $edata = $appsql->getPortalAudit($pid, 'review', 'payment');
}
```
**Category:** A01 Broken Access Control (IDOR)
**Problem:** `getPortalAuditRec($recid)` fetches a payment-audit record purely by primary key with no check that the record belongs to the session's `$pid`. Any authenticated portal user (or anyone able to reach this endpoint with `$ignoreAuth`) can enumerate `recid` values and pull **other patients' payment/credit-card records** (`$ccdata` contains card number, expiry, CVV/`cardCode`, zip). The new `$isPortal` flag is set but never used to scope this lookup.
**Severity:** Critical – full cardholder data disclosure across patients.

### 2. `$pid` is fully attacker-controlled, bypassing the session check that precedes it
**Location:**
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
```
**Category:** A01 Broken Access Control
**Problem:** The script authenticates the portal session and sets `$pid = $_SESSION['pid']`, but then immediately overwrites `$pid` with unauthenticated request parameters. This defeats the entire point of the session check above it and lets an authenticated patient view/post payment data for any other `pid`. This is pre-existing but the diff continues to build the whole payment/PHI/PCI flow on top of it (also touches `getPortalAudit($pid, ...)` and the SQL queries driven by `$pid`).
**Severity:** Critical.

### 3. `form_pid` accepted from POST body without ownership validation
**Location:**
```php
$form_pid = $_POST['form_pid'];
...
frontPayment($form_pid, ...);
... ar_session / ar_activity inserts keyed on $form_pid ...
```
**Category:** A01 Broken Access Control
**Problem:** The patient-id used to record payments and insert `ar_session`/`ar_activity` rows comes directly from client-supplied POST data, never cross-checked against `$_SESSION['pid']`. A malicious portal user can submit payments/adjustments against an arbitrary patient's account.
**Severity:** Critical (financial record tampering, cross-patient data manipulation).

---

## High

### 4. Stored XSS via unescaped card number output
**Location:**
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```
**Category:** A03 Injection (XSS)
**Problem:** `$ccdata["cardNumber"]` is echoed with no `htmlspecialchars()`/`attr()`/`text()` encoding when the "authUserID or transId" condition is true. The field originates from client-submitted form input (`cardNumber`) that is only validated client-side (regex `pattern="\d"` can be trivially bypassed by direct POST). The diff *widens* the exposure condition to `|| isset($ccdata["transId"])`, meaning this unescaped branch can now also be reached by unauthenticated portal patients once a transaction ID exists, not just staff with `authUserID`. This also compounds with Issue #1 (IDOR via `recid`) to make this a reliable stored-XSS + card-disclosure chain.
**Severity:** High.

### 5. Storage of full PAN and CVV (even "encrypted")
**Location:** `$ccdata["cardNumber"]`, `$ccdata["cardCode"]` decrypted from `decryptStandard($edata['checksum'])` and displayed in the UI; `cardCode`/CVV field persisted and later echoed.
**Category:** A02 Cryptographic Failures / A04 Insecure Design
**Problem:** Storing the full card number and CVV (even if encrypted at rest) is a PCI-DSS violation — CVV must never be persisted after authorization. The "manual Authorize" workflow (staff clicks a button to confirm a card already stored server-side) is itself an insecure design pattern for card data handling.
**Severity:** High.

### 6. No server-side bound on payment amount (negative/zero amount bypass)
**Location:**
```php
if ($amount = 0 + $payment) { ... }
```
and the `pre_payment` branch, which uses `$_REQUEST['form_prepayment']` directly as `pay_total` with no validation at all.
**Category:** A04 Insecure Design / Improper Input Validation
**Problem:** Negative-payment prevention ("Negative payments not accepted") is enforced only in client-side JavaScript (`calctotal()`); the server performs no equivalent check, so a crafted POST can insert negative or non-numeric payment/adjustment amounts directly into `ar_activity`/`ar_session`, corrupting the patient ledger.
**Severity:** High.

### 7. No CSRF protection on payment-posting form/AJAX endpoints
**Location:** `<form id="invoiceForm" method='post' ...>`, `$('#paySubmit').click(...)` AJAX to `./lib/paylib.php`, and `$_POST['form_save']` handling.
**Category:** A01 Broken Access Control (CSRF)
**Problem:** No CSRF token is present on the form or the AJAX request. Combined with issues #2/#3 (attacker-controllable `pid`/`form_pid`), a hostile page could force a logged-in portal patient's browser to submit a payment or post an adjustment without consent.
**Severity:** High.

---

## Medium

### 8. Potential leakage of payment gateway API key to the browser
**Location:**
```js
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
**Category:** A02 Cryptographic Failures / Security Misconfiguration
**Problem:** `gateway_api_key` is embedded directly in client-side JS. For Authorize.Net Accept.js this is expected to be the public API Login ID, but the generic naming (`apiKey`) creates risk that a secret/transaction key could be misconfigured into this field and leaked to all page viewers. Needs explicit confirmation/documentation that only the public-safe identifier is ever stored in `$GLOBALS['gateway_api_key']`.
**Severity:** Medium (verify configuration; High if it can ever hold a true secret).

### 9. Inaccurate/weak audit trail for financial postings
**Location:**
```php
array($_SESSION['authId'], $form_source, $amount, $form_pid, $form_method)   // ar_session insert
...
array($form_pid, $enc, ..., $_SESSION['authId'], $session_id, $amount)      // ar_activity insert
```
**Category:** A09 Security Logging and Monitoring Failures
**Problem:** `$_SESSION['authId']` is used (there is no such session key elsewhere in the codebase; the correct key used throughout the rest of the file is `$_SESSION['authUserID']`). This likely evaluates to `null`/empty, meaning `post_user`/`user_id` on financial records will not correctly identify who posted the payment — weakening the audit trail for monetary transactions.
**Severity:** Medium.

### 10. Race condition in manual sequence number generation
**Location:**
```php
sqlBeginTrans();
$sequence_no = sqlQuery("SELECT IFNULL(MAX(sequence_no),0) + 1 ... ");
sqlInsert(... $sequence_no['increment'] ...);
sqlCommitTrans();
```
**Category:** A08 Software and Data Integrity Failures
**Problem:** `SELECT MAX()+1` followed by `INSERT` without `SELECT ... FOR UPDATE` or a unique constraint is a classic TOCTOU race; concurrent requests (plausible for a portal under load or replay) can generate duplicate `sequence_no` values, corrupting the financial ledger for a patient/encounter.
**Severity:** Medium.

### 11. Possible use of outdated jQuery
**Location:**
```php
<script src="<?php echo $GLOBALS['assets_static_relative']; ?>/jquery/dist/jquery.min.js"></script>
```
(replacing `jquery-1-11-3/dist/jquery.js`)
**Category:** A06 Vulnerable and Outdated Components
**Problem:** Can't confirm from the diff whether the referenced `jquery/dist/jquery.min.js` asset was actually upgraded to a patched version. jQuery 1.x has known XSS-relevant issues (e.g., CVE-2015-9251, CVE-2012-6708). Verify the bundled version is current and patched.
**Severity:** Medium (verification needed).

---

## Low / Informational

- **`$ccdata["transId"]` / year concatenation bug** (`$ccdata["transId"]) . "/" . text($ccdata["year"])`) – cosmetic/logic bug, not a vulnerability per se, but indicates insufficient testing around sensitive payment-display code paths.
- **`session_destroy()` without apparent immediate `exit`/redirect shown in the visible diff context** for the non-portal branch – should be double-checked that execution actually halts; otherwise the rest of the script (which assumes `$pid`/session validity) could run in an unauthenticated context.
- Year dropdown list contains a typo (`<option value="2025">2017</option>` in the original, fixed in the diff) – functional only.

---

## Summary

The most serious issues are **broken access control**: the new `recid` parameter introduces a direct IDOR that can expose other patients' stored credit-card data (PAN, CVV), and this combines with pre-existing, unaddressed issues where `$pid` and `form_pid` are taken from client-supplied request data without verifying they match the authenticated portal session. These should block merge until fixed. Additionally, the change widens an existing unescaped-output code path for card numbers into a reachable stored-XSS/sensitive-data-exposure condition for portal (non-staff) sessions. Storage of full card number/CVV, missing CSRF protection, and lack of server-side amount validation are pre-existing but directly relied upon/extended by this change and should also be remediated.