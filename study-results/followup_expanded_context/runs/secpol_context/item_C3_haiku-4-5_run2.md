# Security Review: portal_payment.php

I have identified several **critical security vulnerabilities** in this pull request:

---

## 1. **Broken Access Control (A01:2021)**
**Location:** Lines 27-33 (session validation logic)

**Problem:** The access control relies solely on session variables without proper re-validation:
```php
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
```
- No verification that the patient actually owns the PID they're accessing
- The `$ignoreAuth = true` flag disables subsequent authorization checks
- A patient could potentially access another patient's payment records by manipulating `$_REQUEST['pid']`

**Severity:** **CRITICAL**

---

## 2. **Injection - Insufficient Input Validation (A03:2021)**
**Location:** Line 59

**Problem:**
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
```
While the cast to `(int)` prevents SQL injection here, the value is then used unsafely:
```php
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);  // Line 75
}
```
Without examining `getPortalAuditRec()`, we cannot verify it's parameterized. Additionally, there's no validation that `$recid` belongs to the current patient.

**Severity:** **HIGH**

---

## 3. **Broken Access Control - Payment Record Access (A01:2021)**
**Location:** Lines 74-78

**Problem:**
```php
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
} else {
    $edata = $appsql->getPortalAudit($pid, 'review', 'payment');
}
```
No authorization check verifies that `$recid` belongs to the patient (`$pid`). An attacker could enumerate audit record IDs and access other patients' payment information.

**Severity:** **CRITICAL**

---

## 4. **Cryptographic Failures - Sensitive Data Exposure (A02:2021)**
**Location:** Lines 1232-1254 (payment form HTML)

**Problem:**
```php
<input name="cardNumber" id="cardNumber" type="text" ... autocomplete="off" ... />
<input name="month" id="expMonth" class="form-control">
<input name="year" id="expYear" class="form-control">
<input name="cardCode" id="cardCode" type="text" .../>
```
- Full credit card number is collected in plaintext and transmitted
- While the comment mentions "PCI compliance" via tokenization, the actual form still accepts raw card data
- For non-Stripe/AuthorizeNet modes, card data may be logged or stored without encryption

**Severity:** **CRITICAL**

---

## 5. **Cross-Site Scripting (XSS) - A03:2021**
**Location:** Lines 1255-1259

**Problem:**
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```
- `$ccdata` is decoded from JSON but not escaped: `json_decode(decryptStandard($edata['checksum']), true)`
- If the decrypted data is malicious, it will be reflected in the HTML without `htmlspecialchars()` or `text()`
- Same issue on lines 1260-1262 with `$ccdata["transId"]` and `$ccdata["authCode"]`

**Severity:** **HIGH**

---

## 6. **Security Misconfiguration - Insecure JavaScript (A05:2021)**
**Location:** Lines 1344-1352

**Problem:**
```php
<script type="text/javascript">
    var chargeMsg = <?php $amsg = xl('Payment was successfully authorized...') . "\n" . ...
        echo json_encode($amsg);
    ?>;
    var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
    var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
- API keys and public keys are embedded directly in client-side JavaScript
- Even if the public key is intentionally public, API keys should never be client-accessible
- Inspect element reveals sensitive gateway credentials

**Severity:** **CRITICAL**

---

## 7. **Broken Access Control - Session Hijacking Risk (A01:2021)**
**Location:** Line 22 (global level)

**Problem:**
```php
session_start();
$isPortal = false;
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
```
- No session fixation protection (no regeneration after login)
- No CSRF tokens on form submissions (line 948-950 show form without token)
- The `form_save` POST action has no CSRF protection

**Severity:** **HIGH**

---

## 8. **Injection - Insufficient Output Encoding (A03:2021)**
**Location:** Lines 1220-1222

**Problem:**
```php
<strong><?php echo xlt('Card Holder Zip'); ?>: </strong><span id="czip"><?php echo text($ccdata["zip"]) ?></span><br>
```
While `text()` is used here (good), inconsistently other fields use direct echo:
```php
echo $ccdata["cardNumber"] . "</span><br>";  // Line 1250 - NO ENCODING
```

**Severity:** **MEDIUM** (inconsistent but present in critical data)

---

## 9. **Security Logging and Monitoring Failures (A09:2021)**
**Location:** Lines 209-400 (payment processing)

**Problem:**
- No audit logging of payment transactions
- No logging of failed authorization attempts
- No logging of credit card validation failures
- Payment modifications (lines 226-400) occur without any logging trail
- Amount modifications in `$insert_value` calculations (lines 318-371) are not logged

**Severity:** **MEDIUM**

---

## 10. **Insecure Design - Missing Rate Limiting (A04:2021)**
**Location:** Lines 826-865 (AJAX payment submission)

**Problem:**
```javascript
$('#paySubmit').click(function (e) {
    e.preventDefault();
    $.ajax({
        type: "POST",
        url: liburl,
        data: $("#invoiceForm").serialize() + extra,
```
- No rate limiting on payment attempts
- An attacker could brute-force or repeatedly submit payments
- No throttling mechanism visible

**Severity:** **MEDIUM**

---

## 11. **Vulnerable Component - Outdated jQuery (A06:2021)**
**Location:** Line 447

**Problem:**
```php
<script type="text/javascript" src="<?php echo $GLOBALS['assets_static_relative']; ?>/jquery/dist/jquery.min.js"></script>
```
- The jQuery version is not specified; likely outdated
- Should use a pinned version with known security patches
- jQuery 1.x versions had many XSS vulnerabilities

**Severity:** **MEDIUM**

---

## 12. **Broken Access Control - POST Variable Injection (A01:2021)**
**Location:** Lines 56-59

**Problem:**
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
```
- `$_REQUEST` allows GET/POST/COOKIE manipulation
- Use `$_POST` and `$_GET` explicitly
- No validation that submitted `pid` matches authenticated patient

**Severity:** **HIGH**

---

## Summary

| Severity | Count | Issues |
|----------|-------|--------|
| **CRITICAL** | 4 | Access control (patient isolation), payment record access, card data in plaintext, API keys in JS |
| **HIGH** | 4 | Insufficient input validation, XSS in card data, session hijacking, POST variable injection |
| **MEDIUM** | 4 | Inconsistent output encoding, audit logging, rate limiting, vulnerable jQuery |

**Recommendation:** Do not merge this PR without addressing at minimum the CRITICAL issues, particularly:
1. Add authorization checks for `recid` ownership
2. Remove API keys from JavaScript
3. Implement proper PCI-DSS compliant card tokenization (server-side)
4. Add CSRF tokens to all forms
5. Implement parameterized queries throughout
6. Add comprehensive audit logging