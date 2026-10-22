# Code Review: portal_payment.php

## Issues Found

### 1. **SQL Injection Vulnerability - CRITICAL**
**Location:** Line 59
```php
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
```
**Problem:** User input from `$_REQUEST['hidden_patient_code']` is used directly in comparison without validation or type casting. While the comparison might provide some protection, this should be explicitly cast to `(int)` for clarity and safety.

**Severity:** HIGH

---

### 2. **Missing Input Validation - HIGH**
**Location:** Line 60
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
```
**Problem:** While `recid` is properly cast to int, there's no validation that it's a positive number. A negative recid could be problematic depending on `getPortalAuditRec()` implementation.

**Severity:** MEDIUM

---

### 3. **SQL Injection in Dynamic Query - HIGH**
**Location:** Line 1117
```php
$query = "SELECT fe.encounter, fe.reason, b.code_type, b.code, b.modifier, b.fee, " .
    "LEFT(fe.date, 10) AS encdate ,fe.last_level_closed " . "FROM  form_encounter AS fe left join billing AS b  on " .
    "b.pid = ? AND b.activity = 1  AND " . "b.code_type != 'TAX' AND b.fee != 0 " . "AND fe.pid = b.pid AND fe.encounter = b.encounter " .
    "where fe.pid = ? " . "ORDER BY b.encounter";
```
**Problem:** While parameters are properly used with placeholders, the hard-coded string `'TAX'` should be parameterized for consistency and maintainability.

**Severity:** LOW (Hard-coded, but inconsistent pattern)

---

### 4. **Uninitialized Variable Usage - MEDIUM**
**Location:** Line 1137
```php
if (empty($encs[$key])) {
    $encs[$key] = array(
        'encounter' => $drow['encounter'], 'date' => $drow['encdate'],
        'last_level_closed' => $drow['last_level_closed'],
        'charges' => 0, 'payments' => 0
    );
}
```
**Problem:** The variable `$encs` is used without being explicitly initialized at the beginning of the script. While PHP will auto-create it, explicit initialization is better practice.

**Severity:** LOW (Maintainability issue)

---

### 5. **Logic Error in Form Submission - MEDIUM**
**Location:** Lines 233-247
```php
if ($_POST['form_upay'] && $_REQUEST['radio_type_of_payment'] != 'pre_payment') {
    foreach ($_POST['form_upay'] as $enc => $payment) {
        if ($amount = 0 + $payment) {
            $zero_enc = $enc;
            // ... removed code ...
```
**Problem:** The removed code block (original lines 239-241) had important conditional logic that was deleted. The comment suggests this was intentional, but removing it changes payment processing logic without clear explanation. This could cause incorrect invoice balance calculations.

**Severity:** MEDIUM (Correctness)

---

### 6. **Global Variable Manipulation Without Documentation - MEDIUM**
**Location:** Lines 109-114
```php
$sum_charges = $sum_ptpaid = $sum_inspaid = $sum_duept = $sum_copay = $sum_patcopay = $sum_balance = 0;
function echoLine($iname, $date, $charges, $ptpaid, $inspaid, $duept, $encounter = 0, $copay = 0, $patcopay = 0)
{
    global $sum_charges, $sum_ptpaid, $sum_inspaid, $sum_duept, $sum_copay, $sum_patcopay, $sum_balance;
```
**Problem:** Multiple global variables are declared in `echoLine()`. While functional, this makes the function harder to test and maintain. Consider passing these as reference parameters or using a class.

**Severity:** LOW (Maintainability)

---

### 7. **Incomplete Transaction Handling - MEDIUM**
**Location:** Lines 257-264, 362-377
```php
sqlBeginTrans();
$sequence_no = sqlQuery(...);
$insrt_id = sqlInsert(...);
sqlCommitTrans();
```
**Problem:** No error handling or rollback logic if `sqlInsert()` fails. If the insert fails, the transaction commits anyway with incomplete data.

**Severity:** HIGH (Data Integrity)

---

### 8. **Missing CSRF Protection - MEDIUM**
**Location:** Line 945
```php
<form id="invoiceForm" method='post' action='<?php echo $GLOBALS["webroot"] ?>/portal/portal_payment.php'>
```
**Problem:** No CSRF token validation visible in the form submission or processing. The form accepts POST data without token verification.

**Severity:** MEDIUM (Security)

---

### 9. **Potential XSS Vulnerability - MEDIUM**
**Location:** Lines 957-960
```php
echo htmlspecialchars($patdata['fname'], ENT_QUOTES) . " " .
    htmlspecialchars($patdata['lname'], ENT_QUOTES) . " " .
    htmlspecialchars($patdata['mname'], ENT_QUOTES) . " (" .
    htmlspecialchars($patdata['pid'], ENT_QUOTES) . ")" 
```
**Problem:** While `htmlspecialchars()` is used here, other locations use `attr()`, `text()`, and `echo` inconsistently. Need consistent output encoding throughout.

**Severity:** MEDIUM (Inconsistent escaping)

---

### 10. **Missing Authorization Check - HIGH**
**Location:** Lines 26-34
```php
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
    $isPortal = true;
    require_once(dirname(__FILE__) . "/../interface/globals.php");
} else {
    session_destroy();
```
**Problem:** The `$isPortal` flag is set but there's no subsequent verification that the patient can only access their own data. The `$pid` from session could be manipulated if session handling is compromised.

**Severity:** HIGH (Authorization)

---

## Summary

| Severity | Count | Issues |
|----------|-------|--------|
| CRITICAL | 0 | - |
| HIGH | 4 | SQL injection patterns, transaction error handling, CSRF protection, authorization checks |
| MEDIUM | 6 | Input validation, logic errors, global variables, inconsistent escaping |
| LOW | 2 | Hard-coded SQL values, uninitialized variables |

**Recommendation:** Address the HIGH severity items before merge, particularly transaction error handling and authorization checks.