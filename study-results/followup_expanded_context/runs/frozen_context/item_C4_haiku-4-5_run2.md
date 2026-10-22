# Code Review: interface/forms/eye_mag/report.php

## Issues Found

### 1. **CRITICAL: SQL Injection Vulnerability**
**Location:** Line 63-64
```php
$query  = "SELECT * FROM form_eye_mag_prefs where PEZONE='PREFS' AND id=? ORDER BY ZONE_ORDER,ordering";
$result = sqlStatement($query,array($_SESSION['authUserID']));
```
**Issue:** While this specific query uses parameterized statements correctly, the code later uses `$$LOCATION` (variable variables) on line 69 without sanitization:
```php
$$LOCATION = text($prefs['GOVALUE']);
```
This creates dynamic variable names from database values, which is a security anti-pattern.

**Severity:** HIGH

---

### 2. **CRITICAL: SQL Injection via LIKE Clause**
**Location:** Line 1916
```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
**Issue:** Direct string concatenation in SQL LIKE clause without escaping or parameterized statements. The `$filename` variable is derived from user-controlled `$pid` and `$encounter` without proper sanitization.

**Severity:** CRITICAL

---

### 3. **HIGH: Unvalidated Variable Variables**
**Location:** Lines 69, 88-90, and throughout the file
```php
$$LOCATION = text($prefs['GOVALUE']);
// and later:
@extract($objQuery);  // Line 88
@extract($encounter_data);  // Line 205
```
**Issue:** The `@extract()` function with unsanitized database data creates arbitrary variables in the function scope. Combined with `$$LOCATION` pattern, this enables variable manipulation attacks.

**Severity:** HIGH

---

### 4. **HIGH: Missing Input Validation on REQUEST Parameters**
**Location:** Lines 61-67
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```
**Issue:** 
- Case mismatch: checking `$_REQUEST['CHOICE']` but assigning `$_REQUEST['choice']`
- No validation of data types (should be integers for IDs)
- No sanitization of `$form_name`

**Severity:** HIGH

---

### 5. **HIGH: Unescaped File Paths**
**Location:** Lines 1950-1952, 1994-1996
```php
$from_file = $GLOBALS["fileroot"] . "/sites/" . $_SESSION['site_id'] .
  '/documents/' . $from_pathname . '/' . $from_filename;
```
**Issue:** `$_SESSION['site_id']` is used directly in file path construction without validation. If session data is compromised, arbitrary files could be accessed.

**Severity:** HIGH

---

### 6. **HIGH: Missing CSRF Protection**
**Location:** Line 61-67 (REQUEST parameters)
**Issue:** The form accepts data via `$_REQUEST` but there's no CSRF token validation visible in the code.

**Severity:** MEDIUM-HIGH

---

### 7. **MEDIUM: Inconsistent Output Escaping**
**Location:** Lines throughout (1630, 1640, etc.)
```php
echo xlt('Chief Complaint'); ?>:</b> &nbsp;<?php echo text($CC1);
// but also:
echo $HPI1;  // Line 285 - NOT escaped!
```
**Issue:** Some variables are escaped with `text()` but others are not. Line 285 `$HPI1` is output without escaping.

**Severity:** MEDIUM

---

### 8. **MEDIUM: Potential Path Traversal**
**Location:** Line 1935-1939
```php
$from_all = explode("/",$url_file);
$from_filename = array_pop($from_all);
for ($i=0;$i<$d->get_path_depth();$i++) {
  $from_pathname_array[] = array_pop($from_all);
}
```
**Issue:** No validation that the resulting path stays within intended directory. Symlinks or `..` sequences could escape the documents directory.

**Severity:** MEDIUM

---

### 9. **MEDIUM: Error Suppression Operator Misuse**
**Location:** Lines 88, 205
```php
@extract($objQuery);
@extract($encounter_data);
```
**Issue:** Using `@` to suppress errors hides real problems. If `extract()` fails silently, variables won't be defined, but the code continues.

**Severity:** MEDIUM

---

### 10. **LOW: Deprecated `htmlspecialchars()` Usage**
**Location:** Line 2043
```php
$term = nl2br(htmlspecialchars($term,ENT_NOQUOTES));
```
**Issue:** Should use `htmlspecialchars()` with `ENT_QUOTES` or `ENT_COMPAT` for security. `ENT_NOQUOTES` is explicitly insecure.

**Severity:** LOW

---

### 11. **LOW: Missing Return Type Consistency**
**Location:** Lines 1888, 1955
```php
return;  // Line 295 - returns nothing from eye_mag_report()
return;  // Line 1955 - returns nothing from display_draw_image()
```
**Issue:** Functions that should return values or have clear contracts return nothing inconsistently.

**Severity:** LOW

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1 |
| HIGH     | 6 |
| MEDIUM   | 3 |
| LOW      | 2 |

**Recommendation:** Before merging, address the CRITICAL SQL injection issue (#2) and all HIGH severity issues (#1, #3, #4, #5, #6).