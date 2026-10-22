# Security Review: eye_mag/report.php

## Critical Issues Found

### 1. **SQL Injection Vulnerability**
**Location:** Line 1661  
**Category:** OWASP A03:2021 - Injection  
**Severity:** CRITICAL

```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```

The `$filename` variable is constructed from user-controlled data (`$pid`, `$encounter`) without proper parameterization. Although `$pid` and `$encounter` come from database queries earlier, the concatenation into a LIKE clause is vulnerable.

**Fix:** Use parameterized queries:
```php
$sql = "SELECT * from documents where documents.url like ?";
$doc = sqlQuery($sql, array('%' . $filename . '%'));
```

---

### 2. **SQL Injection via Unvalidated User Input**
**Location:** Lines 63-67  
**Category:** OWASP A03:2021 - Injection  
**Severity:** CRITICAL

```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```

Direct assignment from `$_REQUEST` without validation/sanitization. While `sqlStatement()` uses parameterized queries elsewhere, these variables are used in multiple contexts (lines 84, 252, etc.) without consistent escaping.

**Fix:** Validate and sanitize all user inputs:
```php
if (!empty($_REQUEST['ptid'])) $pid = intval($_REQUEST['ptid']);
if (!empty($_REQUEST['encid'])) $encounter = intval($_REQUEST['encid']);
```

---

### 3. **Broken Access Control - Missing Authorization Checks**
**Location:** Lines 63-69, throughout the file  
**Category:** OWASP A01:2021 - Broken Access Control  
**Severity:** HIGH

No authorization checks are performed to verify the user has permission to access the patient record (`$pid`) or encounter (`$encounter`). The code relies entirely on OpenEMR's global session but makes no explicit ACL verification.

**Fix:** Add explicit access control checks:
```php
require_once(dirname(__FILE__) ."/../../../library/acl.inc");
if (!acl_check('patients', 'med', '', 'view')) {
    die(xlt('Access Denied'));
}
if (!canViewPatient($pid)) {
    die(xlt('Unauthorized access to patient record'));
}
```

---

### 4. **Reflected XSS via Unescaped Output**
**Location:** Lines 1808-1809, and multiple locations  
**Category:** OWASP A03:2021 - Injection  
**Severity:** HIGH

```php
echo "<img src='".$filetoshow."' style='width:50mm;' src='$from_file'><hr style='width:40mm;' />".
$providerNAME."<br />";
```

While `text()` is used in many places, there are instances where HTML attributes contain user data without proper escaping:

```php
<img src='<?php echo $filetoshow; ?>' ...>  // Line 246
```

**Fix:** Use `attr()` for HTML attributes:
```php
<img src='<?php echo attr($filetoshow); ?>' ...>
```

---

### 5. **Path Traversal Vulnerability**
**Location:** Lines 1684-1697  
**Category:** OWASP A01:2021 - Broken Access Control / A03:2021 - Injection  
**Severity:** HIGH

```php
$from_file = $GLOBALS["fileroot"] . "/sites/" . $_SESSION['site_id'] .
'/documents/' . $from_pathname . '/' . $from_filename;
```

The `$from_pathname` and `$from_filename` come from document paths without validation. An attacker could potentially manipulate document metadata to access arbitrary files.

**Fix:** Validate that paths don't contain directory traversal sequences:
```php
if (strpos($from_pathname, '..') !== false || strpos($from_filename, '..') !== false) {
    die(xlt('Invalid file path'));
}
```

---

### 6. **Information Disclosure - Debug/Error Output**
**Location:** Multiple locations  
**Category:** OWASP A01:2021 - Broken Access Control  
**Severity:** MEDIUM

Use of `@extract()` at lines 88, 250 suppresses errors but obscures potential issues. No visible error handling for missing database records.

**Fix:** Replace with explicit variable handling:
```php
if (!empty($objQuery)) {
    foreach ($objQuery as $key => $value) {
        $$key = $value;
    }
}
```

---

### 7. **Insecure Direct Object References (IDOR)**
**Location:** Lines 84, 252-256  
**Category:** OWASP A01:2021 - Broken Access Control  
**Severity:** HIGH

```php
$query="select form_encounter.date as encounter_date,form_eye_mag.* 
        from form_eye_mag ,forms,form_encounter 
        where form_encounter.encounter =? and ... forms.pid =form_eye_mag.pid and form_eye_mag.pid=? ";        
$encounter_data =sqlQuery($query,array($encounter,$pid));
```

While parameterized, there's no verification that the authenticated user is the patient or a provider authorized to view this patient's records.

**Fix:** Add ACL checks before processing:
```php
if (!canViewPatient($pid)) {
    die(xlt('Access Denied'));
}
```

---

### 8. **Unescaped Variable in HTML Context**
**Location:** Line 1808-1809  
**Category:** OWASP A03:2021 - Injection (XSS)  
**Severity:** MEDIUM

```php
echo "<img style='width:50mm;' src='$from_file'>";
```

The `$from_file` contains a file path that could potentially be manipulated if document handling is compromised.

---

## Summary Table

| # | Issue | Category | Severity | Location |
|---|-------|----------|----------|----------|
| 1 | SQL Injection in LIKE clause | A03:2021 | CRITICAL | Line 1661 |
| 2 | Unvalidated user input | A03:2021 | CRITICAL | Lines 63-67 |
| 3 | Missing authorization checks | A01:2021 | HIGH | Throughout |
| 4 | XSS via unescaped attributes | A03:2021 | HIGH | Multiple |
| 5 | Path traversal | A01:2021 | HIGH | Lines 1684-1697 |
| 6 | Information disclosure | A01:2021 | MEDIUM | Lines 88, 250 |
| 7 | IDOR risk | A01:2021 | HIGH | Lines 84, 252 |
| 8 | Unescaped file path in HTML | A03:2021 | MEDIUM | Line 1808 |

---

## Recommendations

1. **Immediate:** Add parameterized query for all dynamic SQL (line 1661)
2. **Immediate:** Add authorization checks for all patient access
3. **High:** Implement input validation for `ptid`, `encid`, `formid`
4. **High:** Review and validate all file path operations
5. **Medium:** Replace `@extract()` with explicit variable assignment
6. **Medium:** Audit all HTML output for proper escaping (`text()`, `attr()`, `xlt()`)