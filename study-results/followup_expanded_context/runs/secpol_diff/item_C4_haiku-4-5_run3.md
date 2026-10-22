# Security Review: eye_mag/report.php

## Critical Issues Found

### 1. **SQL Injection via LIKE Clause**
**Location:** Line 1957  
**OWASP Category:** A03:2021 – Injection  
**Severity:** CRITICAL

```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```

**Problem:** The `$filename` variable is constructed from user-controlled data (`$pid`, `$encounter`) and is directly interpolated into a LIKE clause without parameterized queries. This allows SQL injection.

**Example Attack:** A malicious `$pid` value like `1_1_OU_ZONE_VIEW.jpg' OR '1'='1` would bypass the query logic.

---

### 2. **SQL Injection in Query String (Line 77)**
**Location:** Line 77  
**OWASP Category:** A03:2021 – Injection  
**Severity:** CRITICAL

```php
$query  = "SELECT * FROM form_eye_mag_prefs where PEZONE='PREFS' AND id=? ORDER BY ZONE_ORDER,ordering";
$result = sqlStatement($query,array($_SESSION['authUserID']));
```

**Problem:** While this query uses parameterized queries (good), it assumes `$_SESSION['authUserID']` is always safe. If session data can be manipulated, this is vulnerable. However, there are multiple other queries using direct string interpolation below.

---

### 3. **SQL Injection via Request Parameters**
**Location:** Lines 64-67  
**OWASP Category:** A03:2021 – Injection  
**Severity:** CRITICAL

```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```

**Problem:** These unsanitized request parameters are used directly in SQL queries throughout the file without proper escaping or parameterization.

---

### 4. **Reflected XSS via form_folder Variable**
**Location:** Lines 243, 252, 976, 1019, 1964, 1970  
**OWASP Category:** A03:2021 – Injection (XSS)  
**Severity:** HIGH

```php
<link rel="stylesheet" href="../../forms/<?php echo attr($form_folder); ?>/css/report.css" type="text/css">
<img src="../../forms/<?php echo $form_folder; ?>/images/Amsler_<?php echo attr($AMSLEROS); ?>.jpg"
```

**Problem:** On line 976, `$form_folder` is echoed without `attr()` escaping:
```php
<img src="../../forms/<?php echo $form_folder; ?>/images/Amsler_<?php echo attr($AMSLEROS); ?>.jpg"
```

This is inconsistent with line 252 which properly uses `attr()`. An attacker could inject XSS payload through `$form_folder`.

---

### 5. **Path Traversal Vulnerability**
**Location:** Lines 1964-1970  
**OWASP Category:** A01:2021 – Broken Access Control  
**Severity:** HIGH

```php
$filetoshow = "../../forms/".$form_folder."/images/".$side."_".$zone."_BASE.jpg"; 
if ($PDF_OUTPUT) $filetoshow = $GLOBALS["webroot"] ."/interface/forms/".$form_folder."/images/".$side."_".$zone."_BASE.jpg"; 
```

**Problem:** The `$form_folder` variable is set from request parameters (line 68) without validation. An attacker could use path traversal like `../../../../etc/passwd` to access arbitrary files.

---

### 6. **Improper Output Encoding**
**Location:** Multiple locations (e.g., lines 344, 1832)  
**OWASP Category:** A03:2021 – Injection (XSS)  
**Severity:** MEDIUM

```php
echo  $item['plan']."</div><br />";  // Line 1832
```

**Problem:** Data from `$IMPPLAN_items` is echoed without escaping. While it comes from the database, the database content should still be validated/escaped on output.

---

### 7. **Insecure Direct Object Reference (IDOR)**
**Location:** Lines 64-67, 99-112  
**OWASP Category:** A01:2021 – Broken Access Control  
**Severity:** HIGH

**Problem:** The code uses `$_REQUEST['ptid']` directly to fetch patient data without verifying the user has access to that specific patient. There is no ACL check before displaying sensitive medical information.

```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
// Later: used directly in queries without access control
$encounter_data =sqlQuery($query,array($encounter,$pid));
```

---

### 8. **Missing CSRF Protection**
**Location:** Entire file  
**OWASP Category:** A01:2021 – Broken Access Control  
**Severity:** MEDIUM

**Problem:** The form processes `$_REQUEST` parameters without CSRF token validation.

---

### 9. **Information Disclosure via Error Messages**
**Location:** No visible error handling  
**OWASP Category:** A09:2021 – Security Logging and Monitoring Failures  
**Severity:** MEDIUM

**Problem:** No try-catch blocks or error handling. Direct database queries could expose sensitive information in PHP errors if exposed to users.

---

## Summary Table

| Issue | Location | Category | Severity |
|-------|----------|----------|----------|
| SQL Injection (LIKE clause) | Line 1957 | Injection | CRITICAL |
| SQL Injection (Request params) | Lines 64-67 | Injection | CRITICAL |
| XSS (Unescaped form_folder) | Line 976 | Injection | HIGH |
| Path Traversal | Lines 1964-1970 | Broken Access Control | HIGH |
| IDOR (Patient Access) | Lines 64-67 | Broken Access Control | HIGH |
| Unescaped Output | Line 1832 | Injection | MEDIUM |
| Missing CSRF Protection | Entire file | Broken Access Control | MEDIUM |
| Error Information Disclosure | Global | Logging & Monitoring | MEDIUM |

---

## Recommendations

1. **Use parameterized queries for all SQL statements** – Replace all instances of string interpolation with `?` placeholders
2. **Validate and escape all user input** – Use `text()`, `attr()`, and other OpenEMR escaping functions consistently
3. **Implement access control checks** – Verify user has permission to access `$pid` before processing
4. **Add CSRF tokens** – Validate tokens on all state-changing operations
5. **Use prepared statements** – Particularly for the LIKE query on line 1957
6. **Implement input validation** – Whitelist allowed values for `$form_folder`, `$pid`, `$encounter`