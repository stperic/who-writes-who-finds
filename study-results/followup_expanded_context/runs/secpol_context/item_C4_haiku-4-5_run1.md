# Security Review of `interface/forms/eye_mag/report.php`

I have identified several critical and high-severity security vulnerabilities in this file:

## CRITICAL ISSUES

### 1. **SQL Injection via String Concatenation**
**Location:** Line 748
```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```
**Category:** OWASP A03:2021 - Injection
**Problem:** The `$filename` variable is directly concatenated into the SQL query without parameterization. An attacker could craft a malicious filename to inject SQL code.
**Severity:** CRITICAL

---

### 2. **Multiple SQL Injection Vulnerabilities**
**Location:** Lines 70-71
```php
$query  = "SELECT * FROM form_eye_mag_prefs where PEZONE='PREFS' AND id=? ORDER BY ZONE_ORDER,ordering";
$result = sqlStatement($query,array($_SESSION['authUserID']));
```
**Category:** OWASP A03:2021 - Injection
**Problem:** While this specific query uses parameterization, line 748 (above) does not. Additionally, throughout the file, user input from `$_REQUEST` is used in database queries without consistent sanitization.
**Severity:** CRITICAL

---

### 3. **Cross-Site Scripting (XSS) - Inconsistent Output Escaping**
**Location:** Lines 1923-1930, 1895, and multiple other locations
```php
echo  $item['plan']."</div><br />";
// versus
echo text($PHODVA);
```
**Category:** OWASP A03:2021 - Injection (XSS)
**Problem:** The code inconsistently uses output escaping. The `text()` function is used in many places but NOT in critical areas like `$item['plan']`, `$item['code']`, and `$item['codetext']`. These database values could contain user-controlled data that hasn't been properly sanitized on input.
**Severity:** HIGH

---

### 4. **Unsafe Dynamic Variable Extraction via extract()**
**Location:** Lines 100-101, 141
```php
@extract($objQuery);
@extract($encounter_data);
```
**Category:** OWASP A08:2021 - Software and Data Integrity Failures
**Problem:** The `extract()` function creates variables from array keys without any validation. Combined with `$_REQUEST` input, this could allow attackers to overwrite critical variables. The `@` suppression mask makes debugging harder.
**Severity:** HIGH

---

### 5. **Unvalidated User Input from $_REQUEST**
**Location:** Lines 60-66
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```
**Category:** OWASP A01:2021 - Broken Access Control
**Problem:** User input from `$_REQUEST` is directly assigned to critical variables (`$pid`, `$encounter`, `$form_id`) without any validation, type checking, or ACL verification. No authorization checks confirm the user can access this patient's data.
**Severity:** CRITICAL

---

### 6. **Missing Access Control Verification**
**Location:** Throughout the file
**Category:** OWASP A01:2021 - Broken Access Control
**Problem:** The file accepts `$pid` and `encounter` from user input but never verifies that the authenticated user has permission to view this patient's record. The included ACL library is never used for authorization checks.
**Severity:** CRITICAL

---

### 7. **Path Traversal Vulnerability**
**Location:** Lines 57-58
```php
require_once("../../forms/".$form_folder."/php/".$form_folder."_functions.php");
```
**Category:** OWASP A01:2021 - Broken Access Control
**Problem:** While `$form_folder` is hardcoded to "eye_mag" in this file, the initial assignment allows user control via `$_REQUEST['formname']` on line 65.
**Severity:** HIGH

---

### 8. **Unescaped File Path in URL Construction**
**Location:** Lines 1855-1856
```php
$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=".$doc['id']."&as_file=false&blahblah=".rand();
echo "<img src='".$filetoshow."'>";
```
**Category:** OWASP A03:2021 - Injection (Reflected XSS)
**Problem:** `$pid` is not URL-encoded and is directly concatenated into the URL attribute. If `$pid` contains special characters or quotes, this could break out of the attribute.
**Severity:** MEDIUM

---

### 9. **Unvalidated SQL LIKE Clause**
**Location:** Line 748
```php
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
```
**Category:** OWASP A03:2021 - Injection
**Problem:** Even if `$filename` were escaped, LIKE clauses are vulnerable to wildcard injection. Characters like `%` and `_` have special meaning.
**Severity:** MEDIUM

---

### 10. **Deprecated Error Suppression Operator**
**Location:** Lines 100-101, 141
```php
@extract($objQuery);
@extract($encounter_data);
```
**Category:** OWASP A09:2021 - Logging and Monitoring Failures
**Problem:** The `@` operator suppresses all errors, preventing proper logging and making debugging difficult. Security errors could be silently ignored.
**Severity:** LOW

---

## SUMMARY

| Severity | Count | Issues |
|----------|-------|--------|
| CRITICAL | 3 | SQL Injection (line 748), Unvalidated `$_REQUEST` input, Missing Access Control |
| HIGH | 3 | Inconsistent XSS escaping, `extract()` abuse, Path traversal potential |
| MEDIUM | 2 | URL encoding issues, LIKE injection |
| LOW | 1 | Error suppression |

## RECOMMENDED FIXES

1. **Use parameterized queries throughout:**
   ```php
   $sql = "SELECT * FROM documents WHERE documents.url LIKE ?";
   $doc = sqlQuery($sql, array('%' . $filename . '%'));
   ```

2. **Validate and sanitize all user input:**
   ```php
   $pid = intval($_REQUEST['ptid'] ?? 0);
   $encounter = intval($_REQUEST['encid'] ?? 0);
   if ($pid <= 0 || $encounter <= 0) exit('Invalid parameters');
   ```

3. **Add ACL checks:**
   ```php
   if (!acl_check('patients', 'med', $pid)) {
       die('Unauthorized access');
   }
   ```

4. **Avoid `extract()` - use explicit variable assignment or array access**

5. **Escape all output consistently:**
   ```php
   echo text($item['plan']); // Use text() for HTML context
   ```

6. **URL-encode dynamic URL parameters:**
   ```php
   $filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=" . urlencode($pid);
   ```