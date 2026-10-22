# Security Review: `portal/portal_payment.php`

## Critical / High Severity

### 1. Broken Access Control — IDOR via `recid` parameter
**Location:** 
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
...
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
}
```
**Category:** A01:2021 – Broken Access Control  
**Problem:** `recid` is attacker-controlled and used to directly fetch a payment audit record with no ownership/ACL check tying it back to `$pid` (the session-bound patient) or the authenticated admin user. A portal patient (or anyone with `$ignoreAuth = true` session) can increment `recid` to pull another patient's pending payment record — which, as shown below, includes full credit card data. This is a classic IDOR, compounded by the fact that `getPortalAuditRec()` (not shown) apparently takes only the numeric id with no patient-scoping predicate.  
**Severity:** Critical

---

### 2. Broken Access Control / Cryptographic Failure — Full PAN and CVV disclosed to patient portal
**Location:**
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
...
<strong><?php echo xlt('CVV'); ?>: </strong><span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?></span><br>
```
**Category:** A02:2021 – Cryptographic Failures / A01 – Broken Access Control  
**Problem:** Full card number and CVV are decrypted server-side and echoed to the browser whenever `$_SESSION['authUserID']` is set (i.e., for staff/admin review) or when `transId` exists. Storing/displaying CVV at all is a PCI-DSS violation (CVV must never be stored after authorization, let alone redisplayed). Combined with the IDOR above, any portal session that can reach `getPortalAuditRec` with an arbitrary `recid` can potentially see another patient's full card data if `$_SESSION['authUserID']` happens to be set (e.g., staff browsing then an attacker in a parallel misconfigured session) — but even restricted to staff, persistently storing and re-displaying CVV is a serious compliance/cryptographic-failure issue.  
**Severity:** Critical

---

### 3. Mass-assignment / unauthenticated money manipulation via `$_POST`/`$_REQUEST`
**Location:** Throughout the `form_save` handling block, e.g.:
```php
$form_pid = $_POST['form_pid'];
...
frontPayment($form_pid, 0, $form_method, $form_source, $_REQUEST['form_prepayment'], 0, $timestamp);
```
**Category:** A01:2021 – Broken Access Control  
**Problem:** `form_pid` is taken directly from POST data and used for all subsequent inserts (`ar_session`, `ar_activity`, `billing`) rather than being derived from `$_SESSION['pid']` (the authenticated portal patient). A patient portal session (`$ignoreAuth = true`) could submit an arbitrary `form_pid` and post payments / manipulate billing records for a different patient's encounter. The original `$pid` is overridden earlier by `$_REQUEST['pid']` / `hidden_patient_code'] as well:
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
```
This lets a logged-in portal patient override their own session pid with another patient's ID for query/display and payment posting purposes.  
**Severity:** High

---

### 4. Authentication/session-state confusion — `$isPortal` flag introduced but unused for authorization
**Location:**
```php
$isPortal = false;
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
    $isPortal = true;
    ...
```
**Category:** A07:2021 – Identification and Authentication Failures  
**Problem:** `$isPortal` is set but never subsequently used to restrict which operations a portal (patient) session may perform vs. a staff session — e.g., it does not gate the `$pid` override from `$_REQUEST`, nor the `recid` lookup, nor the CVV/card display logic (which checks only `$_SESSION['authUserID']`). This indicates the authorization model wasn't actually tightened despite adding the flag; it is effectively unused and gives a false sense of access control being enforced.  
**Severity:** High

---

## Medium Severity

### 5. Sensitive data in client-exposed JS variables
**Location:**
```php
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
**Category:** A02:2021 – Cryptographic Failures / A05 – Security Misconfiguration  
**Problem:** `gateway_api_key` is documented (in globals.inc.php) as "The Auth Name or API key for selected account... API Secret for Stripe." If this truly is a secret API key (not just a tokenization/publishable key) being sent to the browser, it is a serious secret-exposure issue — Stripe secret keys must never be client-side. Even for Authorize.Net, the "apiLoginID" is quasi-public, but the comment indicates this same field is overloaded to hold the Stripe secret key, which would be a severe leak. This needs verification against how the field is used per gateway, but the code conflates both uses in one global.  
**Severity:** Medium-High (potentially Critical if Stripe secret key is exposed)

---

### 6. Reflected/stored data rendered without encoding in a few spots
**Location:**
```php
<strong><?php echo xlt('Name on Card'); ?>: </strong><span id="nc"><?php echo text($ccdata["cardHolderName"]) ?></span>
```
and
```php
echo "<button type='submit' class='btn btn-success' form='invoiceForm'>" . xlt('Post Payment') . "</button>";
```
**Category:** A03:2021 – Injection (XSS)  
**Problem:** Most output uses `text()`/`attr()`/`htmlspecialchars()` correctly in this diff (an improvement over before), but verify `$ccdata["zip"]`, `$ccdata["authCode"]`, `$ccdata["transId"]` etc. are also always passed through `text()` — they are in the visible diff, so this is fine; flagging only because `$edata["date"]` is echoed via `text()` consistently too. **No actual XSS found in the reviewed lines** — downgrading this to informational. (Mentioned for completeness since encoding discipline must be verified for every new field added, e.g. `cardHolderName`, `postal_code` are correctly escaped via `attr()`.)

### 7. CSRF — no token on payment form submissions
**Location:** `<form id="invoiceForm" method='post' action='.../portal_payment.php'>` and the AJAX POST to `./lib/paylib.php`.
**Category:** A01:2021 Broken Access Control / insecure design (missing CSRF protection)  
**Problem:** No CSRF token is included in the form or AJAX payload. Combined with session-based `$ignoreAuth` trust and the `form_pid` mass-assignment issue above, a malicious page could potentially trick a logged-in portal patient's browser into submitting a payment-posting request for a different patient/encounter. OpenEMR has a CSRF framework (`CsrfUtils`) elsewhere in the codebase — it should be applied here too.  
**Severity:** Medium (High if combined with #3)

---

## Lower Severity / Pre-existing issues touched by this diff

### 8. Hardcoded/limited year list regression
**Location:**
```php
<option value="2019">2019</option>
...
<option value="2028">2028</option>
```
**Category:** A04:2021 – Insecure Design (minor)  
**Problem:** Not a security vuln per se, but a maintenance smell — hardcoded expiry years will need periodic manual updates; the old code had an outright bug (`<option value="2025">2017</option>`) which this fixes, but a dynamically generated range would be more robust.  
**Severity:** Low (informational)

### 9. Use of outdated jQuery bundled in app
**Location:**
```php
<script type="text/javascript" src="<?php echo $GLOBALS['assets_static_relative']; ?>/jquery/dist/jquery.min.js"></script>
```
**Category:** A06:2021 – Vulnerable and Outdated Components  
**Problem:** The diff changes the path from a pinned `jquery-1-11-3` to a generic `/jquery/dist/jquery.min.js`. Without seeing the actual shipped version, this could still be an old/vulnerable jQuery (1.x is known to have several XSS CVEs in `.html()`/selector handling, e.g. CVE-2020-11022/11023). Recommend confirming the bundled version is current and patched.  
**Severity:** Medium (pending version confirmation)

### 10. Sequence number race condition (integrity, not strictly OWASP-security but worth flagging)
**Location:**
```php
sqlBeginTrans();
$sequence_no = sqlQuery("SELECT IFNULL(MAX(sequence_no),0) + 1 AS increment FROM ar_activity WHERE pid = ? AND encounter = ?", ...);
$insrt_id = sqlInsert(... $sequence_no['increment'] ...);
sqlCommitTrans();
```
**Category:** A08:2021 – Software and Data Integrity Failures  
**Problem:** `SELECT MAX()+1` followed by `INSERT` inside a transaction without `SELECT ... FOR UPDATE` or a unique constraint/auto-increment is subject to race conditions under concurrent requests, potentially causing duplicate `sequence_no` values or lost financial records, corrupting the audit/ledger integrity of patient billing. This pattern repeats three times in the diff.  
**Severity:** Medium

### 11. Inconsistent/missing authorization check reused from original code (pre-existing, still present)
**Location:**
```php
session_start();
$isPortal = false;
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    ...
    $ignoreAuth = true;
```
**Category:** A07:2021 – Identification and Authentication Failures  
**Problem:** `$ignoreAuth = true` disables OpenEMR's normal ACL/auth checks for the entire script for portal sessions. This is pre-existing design but is directly relied upon/extended by this diff (new `recid` and gateway logic execute under `$ignoreAuth`). Any logic flaw downstream (like the IDOR in #1) is now reachable by unauthenticated-relative-to-core-ACL sessions.  
**Severity:** High (pre-existing, but materially relevant to new code's risk)

### 12. No rate limiting / logging around payment submission endpoints
**Category:** A09:2021 – Security Logging and Monitoring Failures  
**Problem:** No logging calls (e.g., `newEvent`/audit logging) are visible around payment creation, authorization display, or the new `recid`-based lookup. Given this handles PCI-scoped data and money movement, failed/successful payment attempts, and access to another record via `recid`, should be logged to the audit trail for forensic purposes. The function `getPortalAuditRec` is not shown but should be checked for a matching audit log entry.  
**Severity:** Medium

---

## Summary Table

| # | Issue | OWASP Category | Severity |
|---|-------|-----------------|----------|
| 1 | IDOR via `recid` exposes other patients' payment/card records | A01 Broken Access Control | Critical |
| 2 | Full PAN + CVV re-displayed from storage | A02 Cryptographic Failures | Critical |
| 3 | `form_pid`/`pid` trusted from request body for financial inserts | A01 Broken Access Control | High |
| 4 | `$isPortal` flag added but not used to enforce restrictions | A07 Auth Failures | High |
| 5 | Potential secret API key exposed to browser via `gateway_api_key` | A02 Cryptographic Failures | Medium–Critical (verify) |
| 6 | Output encoding — verified OK in this diff | A03 Injection | Informational |
| 7 | No CSRF token on payment forms/AJAX | A01 Broken Access Control | Medium |
| 8 | Hardcoded expiry year list | Insecure Design | Low |
| 9 | jQuery version uncertain after path change | A06 Vulnerable Components | Medium |
| 10 | Race condition in sequence_no generation | A08 Data Integrity | Medium |
| 11 | `$ignoreAuth` globally disables ACL for portal | A07 Auth Failures | High |
| 12 | No audit logging around payment/record access | A09 Logging/Monitoring | Medium |

**Top priorities to fix before merge:** #1 (IDOR), #2 (CVV/PAN disclosure — should never store/display CVV at all per PCI-DSS, and PAN should be masked even for staff unless strictly necessary with proper access logging), #3/#4/#11 (trust boundary between patient-portal session and arbitrary `pid`/`recid`), and #5 (confirm no secret key is sent to the client).