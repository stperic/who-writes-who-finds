# Security Review - portal_payment.php

I have identified several critical and high-severity security vulnerabilities in this pull request:

---

## 1. **Broken Access Control - Missing Authorization Check**
**Location:** Lines 59-63 (new code)
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
...
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
}
```
**OWASP Category:** Broken Access Control (A01:2021)
**Problem:** The code accepts a `$recid` parameter from `$_REQUEST` but performs NO authorization check to verify that the current patient (`$pid`) owns this record. An attacker can retrieve payment audit records for ANY patient by guessing or enumerating `recid` values. The `getPortalAuditRec()` method is called without validating ownership.

**Severity:** **CRITICAL**

**Recommendation:** Validate that the retrieved record belongs to the current patient:
```php
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
    if ($edata && $edata['pid'] != $pid) {
        die('Unauthorized access');
    }
}
```

---

## 2. **Cryptographic Failures - Insufficient Output Encoding**
**Location:** Lines 1238-1241
```php
<strong><?php echo xlt('Name on Card'); ?>: </strong><span id="nc"><?php echo text($ccdata["cardHolderName"]) ?></span>
<strong><?php echo xlt('Card Holder Zip'); ?>: </strong><span id="czip"><?php echo text($ccdata["zip"]) ?></span><br>
```
**OWASP Category:** Cryptographic Failures (A02:2021) / XSS (A03:2021)
**Problem:** Credit card data (`cardHolderName`, `zip`, etc.) is being displayed in plaintext HTML on the page. This PII/sensitive data:
- Should NOT be stored unencrypted in session data displayed to the browser
- Creates an XSS vector if `text()` escaping function fails
- Violates PCI-DSS compliance (should be tokenized, never stored)
- The zip code alone can be used for identity theft

**Severity:** **CRITICAL**

**Recommendation:** 
- Never store full card data in plaintext session variables
- Use payment gateway tokenization exclusively
- Only display masked data (last 4 digits)

---

## 3. **Injection - SQL Injection via Unvalidated encounter ID**
**Location:** Lines 232-238
```php
$ResultSearchNew = sqlStatement(
    "SELECT * FROM billing LEFT JOIN code_types ON billing.code_type=code_types.ct_key ".
    "WHERE code_types.ct_fee=1 AND billing.activity!=0 AND billing.pid =? AND encounter=? ORDER BY billing.code,billing.modifier",
    array($form_pid, $enc)
);
```
**OWASP Category:** Injection (A03:2021)
**Problem:** While parameterized queries ARE used here (good), the `$enc` value comes from POST data (`$_POST['form_upay']` keys) without validation. If `$enc` is ever used in a non-parameterized context elsewhere, it's vulnerable. Additionally, `$enc` is never validated as a positive integer.

**Severity:** **HIGH**

**Recommendation:** Validate encounter ID:
```php
$enc = (int)$enc;  // Force integer conversion
if ($enc < 0) {
    die('Invalid encounter');
}
```

---

## 4. **Broken Access Control - Missing Patient ID Validation**
**Location:** Lines 56-58
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
```
**OWASP Category:** Broken Access Control (A01:2021)
**Problem:** The `pid` can be overridden from `$_REQUEST` without validating that the logged-in patient/user owns this PID. A portal user could access another patient's payment records by manipulating the `pid` or `hidden_patient_code` parameter.

**Severity:** **CRITICAL**

**Recommendation:** Only allow portal patients to access their own records:
```php
if ($isPortal && $pid != $_SESSION['pid']) {
    die('Unauthorized access');
}
```

---

## 5. **Security Misconfiguration - Missing CSRF Protection**
**Location:** Lines 210+ (POST form processing)
```php
if ($_POST['form_save']) {
    $form_pid = $_POST['form_pid'];
    // ... processes payment without CSRF token validation
}
```
**OWASP Category:** Security Misconfiguration (A05:2021) / Server-Side Request Forgery (A10:2021)
**Problem:** Payment processing occurs on `$_POST['form_save']` without CSRF token validation. An attacker can craft a malicious webpage that silently submits a payment for an authenticated portal user.

**Severity:** **HIGH**

**Recommendation:** Implement CSRF token validation:
```php
if (!isset($_POST['csrf_token']) || $_POST['csrf_token'] !== $_SESSION['csrf_token']) {
    die('CSRF validation failed');
}
```

---

## 6. **Insecure Design - Sensitive Data in Client-Side JavaScript**
**Location:** Lines 541-549
```javascript
var chargeMsg = <?php $amsg = xl('Payment was successfully authorized...') . "\n" .
    xl("You will be notified when your payment is applied...") . "\n" .
    xl('Until then you will continue to see payment details here.') . "\n" . xl('Thank You.');
    echo json_encode($amsg); // backward compatable 5.0.1
?>;
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
**OWASP Category:** Insecure Design (A04:2021)
**Problem:** API keys and public keys are embedded in client-side JavaScript. While public keys may be intended for client use, storing them this way makes them visible in:
- Browser DevTools
- Page source
- Browser history
- Cached files

**Severity:** **MEDIUM**

**Recommendation:** Load gateway keys via secure API endpoint only, never embed in HTML/JavaScript.

---

## 7. **Cryptographic Failures - Payment Data Logged in Comments**
**Location:** Lines 215-223 (and similar locations)
```php
$NameNew = $patdata['fname'] . " " . $patdata['lname'] . " " . $patdata['mname'];

$payment_id = idSqlStatement(
    "insert into ar_session set ... description = ? ...",
    array(0, $form_pid, $_SESSION['authUserID'], 0, $form_source, $_REQUEST['form_prepayment'], $NameNew, $form_method)
);
```
**OWASP Category:** Cryptographic Failures (A02:2021)
**Problem:** Patient name and payment method are stored unencrypted in the `description` field. While not as sensitive as card data, this creates an audit trail of payment attempts.

**Severity:** **MEDIUM**

---

## 8. **Vulnerable and Outdated Components - jQuery Version**
**Location:** Line 458
```html
<script type="text/javascript" src="<?php echo $GLOBALS['assets_static_relative']; ?>/jquery/dist/jquery.min.js"></script>
```
**OWASP Category:** Vulnerable and Outdated Components (A06:2021)
**Problem:** No version pinning or validation. jQuery version is not specified; could be outdated and contain known vulnerabilities.

**Severity:** **MEDIUM**

**Recommendation:** Pin to a specific version:
```html
<script src=".../jquery-3.6.4.min.js"></script>
```

---

## 9. **Security Logging and Monitoring Failures**
**Location:** Lines 210-380 (payment processing)
**OWASP Category:** Security Logging and Monitoring Failures (A09:2021)
**Problem:** Payment transactions are processed without:
- Logging who initiated the payment
- Logging failed payment attempts
- Monitoring for duplicate payments in short timeframes
- Alerting on unusual payment patterns

**Severity:** **MEDIUM**

**Recommendation:** Add comprehensive logging:
```php
error_log("Payment attempt: PID=$pid, Amount=$amount, User=" . $_SESSION['authUserID']);
```

---

## Summary Table

| Issue | Category | Severity | Location |
|-------|----------|----------|----------|
| Missing authorization on `recid` parameter | Broken Access Control | CRITICAL | Lines 59-63 |
| PID parameter not validated | Broken Access Control | CRITICAL | Lines 56-58 |
| Credit card data displayed in plaintext | Cryptographic Failures | CRITICAL | Lines 1238-1241 |
| Encounter ID lacks validation | Injection | HIGH | Lines 232-238 |
| Missing CSRF protection | Security Misconfiguration | HIGH | Lines 210+ |
| API keys in client JavaScript | Insecure Design | MEDIUM | Lines 541-549 |
| Unencrypted audit trail | Cryptographic Failures | MEDIUM | Lines 215-223 |
| Outdated jQuery | Vulnerable Components | MEDIUM | Line 458 |
| No payment logging/monitoring | Logging Failures | MEDIUM | Lines 210-380 |

**DO NOT MERGE** until critical issues are addressed.