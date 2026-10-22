# Security Review: FhirCareTeamService.php

## Issues Found

### 1. **Injection Vulnerability (Code Injection via lookup_code_descriptions)**
**Location:** Lines 96, 118  
**OWASP Category:** A03:2021 – Injection  
**Problem:** The code calls `lookup_code_descriptions($dataRecordProvider['role_code'])` and `lookup_code_descriptions($dataRecordFacility['facility_taxonomy'])` without validation. If `lookup_code_descriptions()` performs database queries or evaluates the input unsafely, this could lead to SQL injection or code injection. The input data (`$dataRecordProvider['role_code']`, `$dataRecordFacility['facility_taxonomy']`) comes from database records but should still be validated before passing to external functions.

**Severity:** High

**Recommendation:** Validate that `role_code` and `facility_taxonomy` match expected formats before use. Consider whitelisting acceptable code systems and validating code structure.

---

### 2. **Potential XSS via xlt() Output Without Encoding**
**Location:** Lines 97, 101, 118, 123  
**OWASP Category:** A03:2021 – Injection (XSS)  
**Problem:** The `xlt()` function (translation function) is used to set display values in FHIR coding objects without explicit output encoding:
```php
$roleCoding->setDisplay(xlt("Unknown"));
$description = xlt($dataRecordProvider['role_title']);
```
If `xlt()` does not properly escape output and these values are later rendered in HTML/JSON contexts, XSS could occur.

**Severity:** Medium

**Recommendation:** Verify that `setDisplay()` and `xlt()` properly escape output for the target context (JSON/HTML). If not, apply explicit encoding like `htmlspecialchars()`.

---

### 3. **String Parsing Without Bounds Checking**
**Location:** Lines 100, 121  
**OWASP Category:** A01:2021 – Broken Access Control / A04:2021 – Insecure Design  
**Problem:** Code uses `end($codeParts)` after `explode(':', ...)` without validating that the split produced expected results:
```php
$codeParts = explode(':', $dataRecordProvider['role_code']);
$code = end($codeParts);
```
If the code format is malformed or doesn't contain the expected delimiter, this could result in unexpected behavior or the wrong code being extracted.

**Severity:** Medium

**Recommendation:** Validate the code format before parsing. Example:
```php
$codeParts = explode(':', $dataRecordProvider['role_code']);
if (count($codeParts) < 2) {
    // handle error
}
$code = end($codeParts);
```

---

### 4. **Removed Access Control Function**
**Location:** Lines 177–195 (removed `getOne()` method)  
**OWASP Category:** A01:2021 – Broken Access Control  
**Problem:** The `getOne($fhirResourceId, $puuidBind = null)` method was removed entirely. This method had an important security feature: the optional `$puuidBind` parameter allowed restricting visibility to a specific patient. If this functionality was relied upon for access control, its removal could expose data from other patients. The removal of the `getOne` method means direct resource lookups may now bypass patient context filtering.

**Severity:** High

**Recommendation:** Verify that the removal of `getOne()` doesn't break access control. If `getOne()` is still called elsewhere, ensure `searchForOpenEMRRecords()` includes adequate patient context filtering via `$puuidBind`.

---

### 5. **Logic Change in searchForOpenEMRRecords()**
**Location:** Line 189  
**OWASP Category:** A01:2021 – Broken Access Control  
**Problem:** The second parameter to `getAll()` was changed from `false` to `true`:
```php
// Before: return $this->careTeamService->getAll($openEMRSearchParameters, false, $puuidBind);
// After:  return $this->careTeamService->getAll($openEMRSearchParameters, true, $puuidBind);
```
Without seeing the `CareTeamService::getAll()` signature, it's unclear what this boolean flag controls. If it relates to data visibility or filtering, this change could unintentionally expose more data than intended.

**Severity:** Medium–High

**Recommendation:** Document what this parameter controls. Verify that changing it to `true` doesn't bypass any security filters.

---

### 6. **Insufficient Input Validation on Taxonomy Type Check**
**Location:** Line 127  
**OWASP Category:** A04:2021 – Insecure Design  
**Problem:** The code checks `if ($codeParts[0] === "SNOMED-CT")` but `$codeParts` is created by `explode()` without validating the array has elements. This could cause an undefined array key warning/error if the taxonomy format is unexpected.

**Severity:** Low–Medium

**Recommendation:** Add bounds checking:
```php
if (!empty($codeParts) && $codeParts[0] === "SNOMED-CT") {
```

---

## Summary

| Issue | Category | Severity |
|-------|----------|----------|
| Injection via lookup_code_descriptions() | Injection | High |
| Removed getOne() access control | Broken Access Control | High |
| XSS via xlt() output | Injection (XSS) | Medium |
| Logic change in getAll() parameter | Broken Access Control | Medium–High |
| String parsing without validation | Insecure Design | Medium |
| Missing bounds check on taxonomy split | Insecure Design | Low–Medium |

**Recommendation:** Do not merge until the access control implications of removing `getOne()` and changing the `getAll()` parameter are fully understood and tested.