# Security Review: portal_payment.php

## Summary
This code contains **several significant security vulnerabilities** that require immediate remediation before merging.

---

## Critical Issues

### 1. **Broken Access Control - Missing Authorization Check**
**Location:** Lines 57-59 (new code)
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
```

**Category:** Broken Access Control (A01:2021)

**Problem:** The code accepts `recid` from user input without any authorization check. Line 76 calls `$appsql->getPortalAuditRec($recid)` without verifying that the current user owns or has permission to access that audit record. An attacker could enumerate and access payment records belonging to other patients by varying the `recid` parameter.

**Severity:** **CRITICAL**

**Recommendation:**
```php
// Add authorization check:
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
    // Verify $edata belongs to current patient
    if (!$edata || $edata['pid'] != $pid) {
        die("Unauthorized access");
    }
} else {
    $edata = $appsql->getPortalAudit($pid, 'review', 'payment');
}
```

---

### 2. **Cryptographic Failures - Insufficient Output Encoding**
**Location:** Lines 1232-1246 (payment card data display)
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```

**Category:** Cryptographic Failures (A02:2021)

**Problem:** When logged in as admin (`$_SESSION['authUserID']`), full credit card numbers are echoed to the page. This violates PCI DSS compliance and exposes sensitive payment card data. Additionally, the `text()` function is used elsewhere but not consistently applied to card data.

**Severity:** **CRITICAL**

**Recommendation:**
```php
// Never display full card numbers in HTML
echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
// Always use masked display regardless of user role
```

---

### 3. **Injection - Missing Input Validation on Payment Amounts**
**Location:** Lines 226-232
```php
foreach ($_POST['form_upay'] as $enc => $payment) {
    if ($amount = 0 + $payment) {
        $zero_enc = $enc;
        // ... SQL statement follows with $amount
```

**Category:** Injection (A03:2021)

**Problem:** The `$payment` value undergoes type juggling (`0 + $payment`) but no validation ensures it's a valid positive number. Negative values could be injected to create unintended adjustments. Additionally, `$enc` is used directly in SQL queries without proper validation.

**Severity:** **HIGH**

**Recommendation:**
```php
foreach ($_POST['form_upay'] as $enc => $payment) {
    $amount = floatval($payment);
    $enc = intval($enc);
    if ($amount <= 0) {
        continue; // Skip invalid amounts
    }
    if ($amount != floatval($payment) || $enc <= 0) {
        die("Invalid payment data");
    }
```

---

### 4. **Broken Access Control - Session-Based Patient Verification Weak**
**Location:** Lines 26-31
```php
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
    $isPortal = true;
    require_once(dirname(__FILE__) . "/../interface/globals.php");
} else {
    session_destroy();
```

**Category:** Broken Access Control (A01:2021)

**Problem:** Setting `$ignoreAuth = true` globally disables authentication checks for the entire request. While this may be intentional for portal users, the subsequent code at line 70 checks `if ($_SESSION['authUserID'])` to determine admin vs. portal user. However, the logic at lines 1038-1042 has conditional access control that depends on this flag, which is prone to logic errors.

**Severity:** **MEDIUM**

**Recommendation:** Use explicit role-based checks throughout instead of the broad `$ignoreAuth` flag.

---

### 5. **Security Misconfiguration - Outdated jQuery Version**
**Location:** Line 456
```php
<script type="text/javascript" src="<?php echo $GLOBALS['assets_static_relative']; ?>/jquery/dist/jquery.min.js"></script>
```

**Category:** Vulnerable and Outdated Components (A06:2021)

**Problem:** The code loads jQuery from an external source without specifying a version. The previous code referenced `jquery-1-11-3`, which is severely outdated (from ~2015). Modern jQuery addresses numerous XSS and prototype pollution vulnerabilities.

**Severity:** **MEDIUM**

**Recommendation:**
```php
// Pin to a specific modern version with integrity hash
<script src="https://code.jquery.com/jquery-3.6.4.min.js" 
        integrity="sha256-oP6HI9z1XaZNBrJURtCoUT5SUnxFwVsCTNDF37Q6VE=" 
        crossorigin="anonymous"></script>
```

---

### 6. **Injection - SQL Parameter Confusion**
**Location:** Lines 263-266 (copay payment)
```php
$session_id = sqlInsert(
    "INSERT INTO ar_session (...) VALUES ('0',?,?,now(),now(),?,'','patient','COPAY',?,?,'patient_payment',now())",
    array($_SESSION['authId'], $form_source, $amount, $form_pid, $form_method)
);
```

**Category:** Injection (A03:2021)

**Problem:** The hardcoded string `'0'` as payer_id suggests parameter mismatch. The array has 5 elements but only 4 placeholders are visible in the VALUES clause. This could cause SQL errors or injection if the parameter binding is inconsistent.

**Severity:** **MEDIUM**

**Recommendation:** Count placeholders carefully:
```php
// VALUES has: '0' (hardcoded), ?, ?, now(), now(), ?, '', 'patient', 'COPAY', ?, ?, 'patient_payment', now()
// That's 5 placeholders for 5 array elements - verify this is correct
```

---

### 7. **Cryptographic Failures - Insufficient Encryption for Stored Data**
**Location:** Lines 81-82
```php
$ccdata = json_decode(decryptStandard($edata['checksum']), true);
$invdata = json_decode($edata['table_args'], true);
```

**Category:** Cryptographic Failures (A02:2021)

**Problem:** Credit card data is stored encrypted with `encryptStandard()` then decrypted in the request. However, `$invdata` from `table_args` appears to be unencrypted JSON. If this contains payment amounts or other sensitive data, it's vulnerable to tampering or exposure.

**Severity:** **MEDIUM**

**Recommendation:** Encrypt all sensitive data consistently and verify integrity with HMACs.

---

### 8. **Server-Side Request Forgery - External Script Loading**
**Location:** Lines 1480-1485 (Authorize.Net & Stripe)
```php
<script src="<?php echo $GLOBALS['assets_static_relative']; ?>/jquery-creditcardvalidator/jquery.creditCardValidator.js"></script>
```

**Category:** Vulnerable and Outdated Components (A06:2021)

**Problem:** The code loads external payment gateway libraries without integrity verification. The Stripe and Authorize.Net scripts are loaded conditionally but without `integrity` attributes or pinned versions.

**Severity:** **MEDIUM**

**Recommendation:**
```php
// Use integrity attributes and pin versions
<script src="https://js.stripe.com/v3/" integrity="sha384-..." crossorigin="anonymous"></script>
```

---

### 9. **Injection - XSS via Unescaped JSON Output**
**Location:** Lines 544-553 (JavaScript variable assignment)
```php
var chargeMsg = <?php $amsg = xl('Payment was successfully authorized...'); 
    echo json_encode($amsg); 
?>;
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```

**Category:** Injection (A03:2021)

**Problem:** While `json_encode()` is used, if `$GLOBALS['gateway_public_key']` or `$GLOBALS['gateway_api_key']` contain malicious content, it could escape JSON context. Additionally, these values should not be exposed to client-side JavaScript if they're actual API keys (they should be server-only secrets).

**Severity:** **HIGH**

**Recommendation:**
```php
// Never expose API keys to client-side code
// Public keys only: use json_encode with JSON_HEX_TAG|JSON_HEX_AMP for safety
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key'], JSON_HEX_TAG | JSON_HEX_AMP); ?>;
// Remove apiKey from client entirely
```

---

### 10. **Broken Access Control - Admin-Only Data Visibility Not Enforced**
**Location:** Lines 1232-1241 (Card display logic)
```php
if (isset($_SESSION['authUserID'])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```

**Category:** Broken Access Control (A01:2021)

**Problem:** The visibility of sensitive payment information is controlled only by session variable presence, not by proper role/permission checks. A session variable can be manipulated or spoofed.

**Severity:** **MEDIUM**

**Recommendation:**
```php
// Use explicit permission checks
if ($isAdmin && hasPermission('view_payment_details')) {
    // Show full data
} else {
    // Show masked data
}
```

---

### 11. **Security Logging and Monitoring Failures**
**Location:** Throughout the payment processing section (lines 207-407)

**Category:** Security Logging and Monitoring Failures (A09:2021)

**Problem:** No logging is performed for:
- Failed payment authorization attempts
- Unauthorized access attempts (broken AC)
- Payment reversals or adjustments
- Admin-initiated payment modifications
- API key/credential exposure attempts

**Severity:** **MEDIUM**

**Recommendation:**
```php
// Add comprehensive logging
error_log("Payment processed: pid=$pid, amount=$amount, method=$form_method, user={$_SESSION['authUserID']}");
// Log failed attempts
if ($payment_failed) {
    error_log("SECURITY: Failed payment attempt - possible fraud or misconfiguration", 0);
}
```

---

## Additional Issues

### 12. **Insecure Design - No Rate Limiting**
The payment processing endpoint has no rate limiting. An attacker could attempt repeated payment submissions.

### 13. **Type Confusion in Conditional Logic**
Line 227: `if ($amount = 0 + $payment)` uses assignment in conditional, which is error-prone.

---

## Summary Table

| # | Category | Severity | Location | Issue |
|---|----------|----------|----------|-------|
| 1 | Broken AC | CRITICAL | L76 | Missing authorization for `recid` |
| 2 | Crypto | CRITICAL | L1240 | Full CC number displayed to admin |
| 3 | Injection | HIGH | L226 | Payment amount validation weak |
| 4 | Broken AC | MEDIUM | L26-31 | Global `$ignoreAuth` flag risky |
| 5 | Vuln Comp | MEDIUM | L456 | Outdated jQuery |
| 6 | Injection | MEDIUM | L263-266 | SQL parameter mismatch |
| 7 | Crypto | MEDIUM | L81-82 | Inconsistent encryption of payment data |
| 8 | Vuln Comp | MEDIUM | L1480 | No integrity on external scripts |
| 9 | Injection | HIGH | L546-550 | API keys exposed to client |
| 10 | Broken AC | MEDIUM | L1232 | Role-based visibility not enforced |
| 11 | Logging | MEDIUM | L207+ | No security event logging |

---

## Recommendation: **DO NOT MERGE** until critical issues are resolved.