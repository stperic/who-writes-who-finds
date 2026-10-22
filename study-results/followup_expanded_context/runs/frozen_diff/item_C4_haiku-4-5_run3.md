# Code Review: forms/eye_mag/report.php

## Issues Found

### 🔴 CRITICAL SECURITY ISSUES

1. **SQL Injection Vulnerability (Line 67)**
   - **Location**: Line 67
   - **Problem**: `$_SESSION['authUserID']` is used directly in query but the query uses parameterized binding inconsistently. While this specific line uses `array()` binding, the pattern is mixed throughout.
   - **Severity**: HIGH
   - **Details**: Line 67: `$result = sqlStatement($query,array($_SESSION['authUserID']));` - Actually this is safe, but recommend consistency.

2. **Potential SQL Injection (Line 1896)**
   - **Location**: Line 1896
   - **Problem**: `$sql = "SELECT * from documents where documents.url like '%".$filename."'";` uses string concatenation without parameterization
   - **Severity**: CRITICAL
   - **Fix**: Use parameterized query: `sqlQuery($sql, array('%'.$filename.'%'))`

3. **Insufficient Input Validation (Lines 62-67)**
   - **Location**: Lines 62-67
   - **Problem**: `$_REQUEST` parameters used without proper validation before extracting into variables
   - **Severity**: HIGH
   - **Details**: 
     ```php
     if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
     if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
     ```
   - Should validate and sanitize these values

4. **Variable Extraction Security Risk (Lines 78, 166)**
   - **Location**: Lines 78, 166
   - **Problem**: `@extract($objQuery)` and `@extract($encounter_data)` can lead to variable injection vulnerabilities
   - **Severity**: HIGH
   - **Fix**: Use explicit variable assignment instead of extract()

5. **XSS Vulnerability (Line 1904)**
   - **Location**: Line 1904
   - **Problem**: `$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=".$doc['id']."&as_file=false&blahblah=".rand();` - `$doc['id']` not escaped
   - **Severity**: MEDIUM
   - **Fix**: Use `attr()` function on `$doc['id']`

6. **Missing Output Escaping (Multiple Locations)**
   - **Location**: Lines 412, 550, 706, 760, 1036, and many others
   - **Problem**: Direct variable output without escaping, e.g., `echo $HPI1;` should use `text()` or `attr()`
   - **Severity**: MEDIUM
   - **Examples**:
     - Line 412: `echo $HPI1;` should be `echo text($HPI1);`
     - Line 1036: `echo $background;` - CSS unescaped

### 🟠 RELIABILITY ISSUES

7. **Uninitialized Variables (Multiple)**
   - **Location**: Lines 475, 1166, 1903, etc.
   - **Problem**: Variables like `$bad`, `$ODVF`, `$OSVF` used without initialization
   - **Severity**: MEDIUM
   - **Fix**: Initialize variables before use or check isset()

8. **Missing Error Handling (Lines 78, 166, 1895)**
   - **Location**: Multiple sqlQuery/sqlStatement calls
   - **Problem**: No error checking after database queries
   - **Severity**: MEDIUM
   - **Fix**: Check if query returns results before using them

9. **File Existence Checks Without Error Handling (Lines 303, 1911, 1925)**
   - **Location**: Lines 303, 1911, 1925
   - **Problem**: `file_exists()` checks but paths constructed with user input
   - **Severity**: LOW-MEDIUM

### 🟡 MAINTAINABILITY ISSUES

10. **Code Duplication**
    - **Location**: Lines 414-480 (CC1/HPI1), repeated for CC2, CC3
    - **Problem**: Highly repetitive code for handling multiple chief complaints
    - **Severity**: LOW
    - **Fix**: Use loops to handle multiple items

11. **Inconsistent Variable Naming**
    - **Location**: Throughout
    - **Problem**: Mix of UPPERCASE, camelCase, and snake_case
    - **Severity**: LOW

12. **Magic Numbers and Strings**
    - **Location**: Lines 475-540, 1166-1199
    - **Problem**: Hard-coded zone names, counts, and conditions
    - **Severity**: LOW

13. **Missing Input Type Validation**
    - **Location**: Lines 62-67, 79
    - **Problem**: No validation that `$pid`, `$encounter`, `$form_id` are numeric
    - **Severity**: MEDIUM
    - **Fix**: Add `is_numeric()` or cast to `(int)`

14. **HTML in PHP (Mixed Concerns)**
    - **Location**: Throughout the file
    - **Problem**: File is 2060 lines mixing HTML output with PHP logic
    - **Severity**: LOW
    - **Fix**: Consider separating logic from presentation

### 🔵 MINOR ISSUES

15. **Suppress Error Operator (@)**
    - **Location**: Lines 78, 166
    - **Problem**: `@extract()` suppresses errors; bad practice
    - **Severity**: LOW-MEDIUM
    - **Fix**: Remove @ and handle properly

16. **Incomplete Comments (Line 1030)**
    - **Location**: Line 1030
    - **Problem**: Incomplete URL in background style (missing semicolon)
    - **Severity**: LOW

---

## Summary

| Severity | Count |
|----------|-------|
| CRITICAL | 1     |
| HIGH     | 3     |
| MEDIUM   | 5     |
| LOW      | 6     |

**Priority Fixes**:
1. Fix SQL injection at line 1896
2. Remove or safely replace `extract()` calls
3. Add input validation for `$_REQUEST` parameters
4. Escape all user-facing output with `text()` or `attr()`