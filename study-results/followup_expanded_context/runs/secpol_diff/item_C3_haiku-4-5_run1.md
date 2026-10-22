# Security Review - Portal Payment Page

I have identified several **critical and high-severity security vulnerabilities** in this code:

---

## Critical Issues

### 1. **Broken Access Control - Missing Authorization Check**
**Location:** Lines 58-59
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
```
**Category:** OWASP A01:2021 - Broken Access Control

**Problem:** The `$pid` is overwritten from user-controllable `$_REQUEST` parameters without validating that the authenticated patient/user has access to this patient record. An attacker could manipulate the `pid` parameter to access another patient's payment information.

**Severity:** 🔴 **CRITICAL**

---

### 2. **SQL Injection via Unvalidated recid Parameter**
**Location:** Lines 60, 73-77
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
...
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
}
```
**Category:** OWASP A03:2021 - Injection

**Problem:** While the `(int)` cast provides some protection, the `getPortalAuditRec()` function is called without verification that the user owns this audit record. An attacker could enumerate audit records from other patients by guessing `recid` values.

**Severity:** 🔴 **CRITICAL**

---

### 3. **Broken Access Control - No Patient Record Ownership Validation**
**Location:** Throughout the file, especially lines 205-410

**Problem:** The code processes POST data for payment submission without verifying that the payment is being made by the actual patient or an authorized representative. The check at lines 26-28 only verifies the session exists but doesn't validate the `$_SESSION['pid']` matches the current request's `$pid` after it's been modified from `$_REQUEST`.

**Severity:** 🔴 **CRITICAL**

---

### 4. **Cross-Site Scripting (XSS) - Stored Unescaped Data from Database**
**Location:** Lines 1242-1255
```php
echo '<strong><?php echo xlt('Card Name'); ?>: </strong><span id="cn"><?php echo text($ccdata["cc_type"]) ?></span><br>';
echo '<strong><?php echo xlt('Name on Card'); ?>: </strong><span id="nc"><?php echo text($ccdata["cardHolderName"]) ?></span>';
```
**Category:** OWASP A03:2021 - Injection (XSS)

**Problem:** While `text()` is used here, earlier in the code at line 82, credit card data from the database is decoded without proper sanitization:
```php
$ccdata = json_decode(decryptStandard($edata['checksum']), true);
```
If the encrypted data was compromised or manipulated, malicious JavaScript could be stored and executed.

**Severity:** 🔴 **CRITICAL** (if encryption is compromised) / 🟠 **HIGH** (defense in depth)

---

### 5. **Sensitive Data Exposure - Credit Card Storage**
**Location:** Lines 82-83, 1242-1255
```php
$ccdata = json_decode(decryptStandard($edata['checksum']), true);
$invdata = json_decode($edata['table_args'], true);
```
**Category:** OWASP A02:2021 - Cryptographic Failures

**Problem:** 
- Credit card data (full card number, CVV) is stored in the database at all, even if encrypted. This violates PCI-DSS standards.
- The code displays full credit card numbers to admin users (line 1244), which is non-compliant.
- The encryption method (`decryptStandard()`) is not validated to use industry-standard algorithms.

**Severity:** 🔴 **CRITICAL**

---

## High-Severity Issues

### 6. **Broken Access Control - Admin Bypass**
**Location:** Lines 70-73, 1245
```php
if ($_SESSION['authUserID']) {
    // loads admin user data
}
// Later:
if (isset($_SESSION['authUserID'])) {
    echo $ccdata["cc_number"] . "</span><br>";  // Shows full card number
}
```
**Category:** OWASP A01:2021 - Broken Access Control

**Problem:** Admin users can see and authorize payments for any patient. There's no role-based access control (RBAC) or audit trail to prevent a malicious admin from stealing patient data.

**Severity:** 🟠 **HIGH**

---

### 7. **Insecure Direct Object Reference (IDOR)**
**Location:** Lines 73-77, 1103-1210
```php
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
}
```
**Category:** OWASP A01:2021 - Broken Access Control

**Problem:** No code validates that `$recid` belongs to the patient in `$_SESSION['pid']`. An attacker could iterate through `recid` values to access other patients' payment records.

**Severity:** 🟠 **HIGH**

---

### 8. **Missing CSRF Protection**
**Location:** Lines 960, 1211 (form submission)
```php
<form id="invoiceForm" method='post' action='<?php echo $GLOBALS["webroot"] ?>/portal/portal_payment.php'>
```
**Category:** OWASP A01:2021 - Broken Access Control

**Problem:** No CSRF tokens (`nonce` or similar) are present in the form. An attacker could trick a patient into submitting unauthorized payments via a malicious website.

**Severity:** 🟠 **HIGH**

---

### 9. **Insufficient Logging and Monitoring**
**Location:** Lines 205-410 (payment processing)
```php
if ($_POST['form_save']) {
    // Processes payment without logging WHO made the change
    $payment_id = idSqlStatement(...);
}
```
**Category:** OWASP A09:2021 - Security Logging and Monitoring Failures

**Problem:** 
- No audit logs record which user submitted payment or from which IP address
- No fraud detection for unusual payment patterns
- No alerts for admin authorization of payments

**Severity:** 🟠 **HIGH**

---

### 10. **Server-Side Request Forgery (SSRF) Risk - Third-Party Gateway Integration**
**Location:** Lines 1435-1660 (AuthorizeNet, Stripe integration)
```php
Accept.dispatchData(secureData, acceptResponseHandler);
stripe.createToken(card).then(function (result) { ... });
```
**Category:** OWASP A10:2021 - Server-Side Request Forgery

**Problem:** 
- API keys are embedded in JavaScript (lines 563-564):
```php
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
- If the API key is a secret key (not just public), it's exposed to the client.
- No validation that `$GLOBALS['payment_gateway']` is properly configured.

**Severity:** 🟠 **HIGH**

---

### 11. **Sensitive Data Exposure - Unencrypted AJAX Transmission**
**Location:** Lines 838-865
```javascript
$.ajax({
    type: "POST",
    url: liburl,
    data: $("#invoiceForm").serialize() + extra,
    // No HTTPS enforcement, no encryption of payment data
});
```
**Category:** OWASP A02:2021 - Cryptographic Failures

**Problem:** 
- No enforcement that transmission is over HTTPS (should use CSP and HSTS headers)
- Payment data in `extra` contains serialized form objects with sensitive information
- No integrity verification (HMAC or signatures)

**Severity:** 🟠 **HIGH**

---

### 12. **Authentication Bypass - Session Fixation**
**Location:** Lines 26-31
```php
session_start();
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
```
**Category:** OWASP A07:2021 - Identification and Authentication Failures

**Problem:** 
- The session is started before any CSRF tokens or additional validation.
- `$ignoreAuth = true` is set without verifying session validity or IP consistency.
- No session regeneration after authentication.

**Severity:** 🟠 **HIGH**

---

## Medium-Severity Issues

### 13. **Insufficient Input Validation - Amount Validation**
**Location:** Lines 231, 232
```php
if ($amount = 0 + $payment) {  // Dangerous: assignment in conditional
    $zero_enc = $enc;
```
**Category:** OWASP A01:2021 - Broken Access Control / A03:2021 - Injection

**Problem:** 
- Uses assignment (`=`) instead of comparison (`==`)
- No validation that payment amount is positive or doesn't exceed patient balance
- Could allow negative payments (refunds) without authorization

**Severity:** 🟡 **MEDIUM**

---

### 14. **Weak Encryption Key Management**
**Location:** Lines 82-83
```php
$ccdata = json_decode(decryptStandard($edata['checksum']), true);
```
**Category:** OWASP A02:2021 - Cryptographic Failures

**Problem:** 
- No evidence that encryption keys are properly managed (rotated, stored securely)
- `decryptStandard()` function not reviewed; may use weak algorithms
- No key derivation function visible

**Severity:** 🟡 **MEDIUM**

---

### 15. **Race Condition - Sequence Number Management**
**Location:** Lines 261-267, 360-377
```php
$sequence_no = sqlQuery("SELECT IFNULL(MAX(sequence_no),0) + 1 AS increment FROM ar_activity WHERE pid = ? AND encounter = ?", array($form_pid, $enc));
$insrt_id=sqlInsert(
    "INSERT INTO ar_activity (...sequence_no...) VALUES (...,?,...)",
    array(..., $sequence_no['increment'], ...)
);
```
**Category:** OWASP A01:2021 - Broken Access Control (Software Integrity)

**Problem:** 
- No locking mechanism between SELECT and INSERT
- Multiple concurrent requests could generate duplicate `sequence_no` values
- Transaction doesn't prevent the race condition (should use `FOR UPDATE`)

**Severity:** 🟡 **MEDIUM**

---

### 16. **Missing Output Encoding - JavaScript Context**
**Location:** Lines 563-568, 1351, 1361
```javascript
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var chargeMsg = <?php $amsg = xl('Payment was successfully...'); echo json_encode($amsg); ?>;
```
**Category:** OWASP A03:2021 - Injection (XSS)

**Problem:** While `json_encode()` provides some protection, it can still produce JavaScript-interpreted output if not in proper context. Should use additional escaping.

**Severity:** 🟡 **MEDIUM**

---

## Recommendations

1. **Add authorization check:** Verify `$_SESSION['pid']` matches requested `$pid` before processing any payment.
2. **Add CSRF tokens:** Use nonces in all forms.
3. **Never store full credit card data:** Tokenize immediately, store only tokens.
4. **Implement RBAC:** Restrict admin payment authorization to specific roles.
5. **Add comprehensive audit logging:** Log all payments with user ID, IP, timestamp, and outcome.
6. **Use prepared statements consistently:** All SQL queries are already parameterized, which is good.
7. **Enforce HTTPS:** Use HSTS headers and CSP.
8. **Review encryption:** Use AES-256 with proper key management for any stored sensitive data.
9. **Add rate limiting:** Prevent payment spam attacks.
10. **Implement proper error handling:** Don't expose database errors to users.