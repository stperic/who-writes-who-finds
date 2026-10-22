# Security Review of FhirCareTeamService.php Pull Request

## Summary
I identified **3 security issues** in this code:

---

## Issues Found

### 1. **Improper Input Validation on Code Parsing**
**Location:** Lines 103-110 (facility role taxonomy parsing) and similar code at lines 95-100 (provider role code parsing)

**OWASP Category:** A03:2021 – Injection

**Problem:**
```php
$codeParts = explode(':', $dataRecordProvider['role_code']);
$code = end($codeParts);
$roleCoding->setCode($code);
```

The code uses `explode()` to parse codes from the database, but there is no validation that:
- The code format is actually as expected (contains ':' separator)
- The resulting code part is a valid FHIR code format
- The code doesn't contain malicious content (e.g., XSS payloads if rendered in HTML)

An attacker who can manipulate `dataRecordProvider['role_code']` in the database could inject arbitrary strings into the FHIR response. While this is JSON, if the output is later rendered in an HTML context, it could lead to XSS.

**Severity:** Medium

**Recommendation:** Validate the code format against a whitelist or regex pattern before using it.

---

### 2. **Unsafe Use of lookup_code_descriptions() Without Escaping**
**Location:** Lines 97-99 and Lines 77-79

**OWASP Category:** A03:2021 – Injection / A04:2021 – Insecure Design

**Problem:**
```php
$description = lookup_code_descriptions($dataRecordProvider['role_code']);
if (empty($description)) {
    $description = xlt($dataRecordProvider['role_title']);
}
$roleCoding->setDisplay($description);
```

The `lookup_code_descriptions()` function result is used directly without escaping. While the fallback uses `xlt()` (translation function), the primary path does not. If the database contains unescaped HTML or script content in the code descriptions, it could be returned in the FHIR JSON response.

Additionally, at line 78, `$dataRecordProvider['role_title']` is passed to `xlt()` but there's no guarantee the database field contains safe data.

**Severity:** Medium

**Recommendation:** Explicitly escape output:
```php
$description = htmlspecialchars(lookup_code_descriptions($dataRecordProvider['role_code']), ENT_QUOTES, 'UTF-8');
```

---

### 3. **Status Validation Logic is Incomplete**
**Location:** Lines 82-86

**OWASP Category:** A05:2021 – Security Misconfiguration

**Problem:**
```php
if (array_search($dataRecord['status'], self::CARE_TEAM_STATII) !== false) {
    $careTeamResource->setStatus($dataRecord['status']);
} else {
    $careTeamResource->setStatus(self::CARE_TEAM_STATUS_ACTIVE);
}
```

While this validates the status against an allowlist, `array_search()` with strict comparison (`!== false`) is the correct approach here. However, there is no validation that `$dataRecord['status']` is a string or exists in the array. If `$dataRecord['status']` is `null`, `array_search()` may return unexpected results. Additionally, this validation should ideally happen in the database layer or service layer, not the presentation layer.

**Severity:** Low

**Recommendation:** Add explicit type checking:
```php
if (isset($dataRecord['status']) && is_string($dataRecord['status']) 
    && array_search($dataRecord['status'], self::CARE_TEAM_STATII, true) !== false) {
```

---

### 4. **Potential Data Exposure Through Changed Method Signature**
**Location:** Line 189 – `searchForOpenEMRRecords()` parameter change

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:**
The second parameter to `careTeamService->getAll()` was changed from `false` to `true`:
```php
// Before:
return $this->careTeamService->getAll($openEMRSearchParameters, false, $puuidBind);
// After:
return $this->careTeamService->getAll($openEMRSearchParameters, true, $puuidBind);
```

Without seeing the `CareTeamService::getAll()` signature, it's unclear what this boolean flag controls. If it enables returning additional sensitive data, this could cause information disclosure.

**Severity:** Medium (depends on what the flag controls)

**Recommendation:** Document what this parameter does and verify the change doesn't expose unintended data.

---

### 5. **Removed getOne() Method – Access Control Regression**
**Location:** Lines 184-201 (removed method)

**OWASP Category:** A01:2021 – Broken Access Control

**Problem:**
The `getOne()` method was removed. This method appeared to have custom access control logic with the `$puuidBind` parameter to restrict visibility. By removing this override, the code now relies on the base class implementation in `FhirServiceBase::getOne()`.

While the base class version exists and attempts to handle `puuidBind`, removing the override means:
1. Custom business logic specific to care teams is lost
2. Any patient-scoping logic specific to this resource is delegated entirely to the base class
3. There's no opportunity for resource-specific access control validation

**Severity:** Medium

**Recommendation:** Document why this method was removed and verify the base class implementation provides equivalent access control.

---

## Summary Table

| Issue | Category | Severity | Line(s) |
|-------|----------|----------|---------|
| Code parsing without validation | Injection | Medium | 95-110 |
| Unescaped output from lookup functions | Injection | Medium | 97-99, 77-79 |
| Incomplete status validation | Misconfiguration | Low | 82-86 |
| Unclear parameter change to getAll() | Broken Access Control | Medium | 189 |
| Removed getOne() custom validation | Broken Access Control | Medium | 184-201 (removed) |