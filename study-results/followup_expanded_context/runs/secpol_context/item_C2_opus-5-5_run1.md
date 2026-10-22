# Security Review: `FhirCareTeamService.php`

## Finding 1: Patient-scoped access control is bypassed

**Severity:** High
**OWASP category:** A01:2021 – Broken Access Control
**Location:** `FhirCareTeamService` class declaration and removed `getOne()`, together with `FhirServiceBase::getOne()` and `FhirServiceBase::createOpenEMRSearchParameters()`

### Before this change

`FhirCareTeamService::getOne()` passed `$puuidBind` directly to `CareTeamService::getOne($fhirResourceId, $puuidBind)`. The underlying service then limited results to the bound patient.

### After this change

The override is deleted, so the base class `getOne()` is used instead. The base class only applies the patient restriction when the service is an `IPatientCompartmentResourceService`:

```php
// getOne()
if (isset($puuidBind) && $this instanceof IPatientCompartmentResourceService) { ... }

// createOpenEMRSearchParameters()
if (!empty($puuidBind) && $this instanceof IPatientCompartmentResourceService) { ... }
```

`FhirCareTeamService` only implements `IResourceUSCIGProfileService`. It defines `getPatientContextSearchField()` but never declares `IPatientCompartmentResourceService`. As a result, both `instanceof` checks are false and `$puuidBind` is silently ignored.

Also, `FhirServiceBase::getAll()` calls `searchForOpenEMRRecords($oeSearchParameters)` without `$puuidBind`. So the `$puuidBind` argument passed to `careTeamService->getAll(...)` is always null and offers no fallback protection.

### Impact

A caller limited to one patient can read other patients' care teams. This includes patient-portal users and SMART-on-FHIR apps with a `patient/*` scope or launch context. They can:

- Request `GET /fhir/CareTeam/{uuid}` for any care team UUID.
- Search `GET /fhir/CareTeam` with no parameters to list every care team in the system.
- Search `GET /fhir/CareTeam?patient=<other-patient-uuid>`.

The exposed data is PHI: which patients are linked to which practitioners, organizations, and care roles. This is a regression from the previous code.

### Fix

Declare the interface so the base class enforces the patient binding:

```php
class FhirCareTeamService extends FhirServiceBase implements IResourceUSCIGProfileService, IPatientCompartmentResourceService
```

Additional recommendations:

- Add a regression test showing that a patient-bound request cannot retrieve another patient's CareTeam, either by `_id` or by search.
- As defense in depth, consider having `FhirServiceBase` fail closed. For example, throw an error or return no results when `$puuidBind` is set but the service does not implement `IPatientCompartmentResourceService`, rather than silently dropping the restriction. This would catch the same mistake in other resources.

## Finding 2: Change from OR to AND search logic is an improvement

**Severity:** Positive change (no issue)
**Location:** `searchForOpenEMRRecords()`

Changing `getAll(..., false, ...)` to `getAll(..., true, ...)` makes search conditions combine with AND. Under the old OR behavior, an injected patient filter would have been OR'd with the user's other criteria, which could defeat it. This change is necessary for the fix in Finding 1 to actually work, so it should be kept.

## Minor notes (not vulnerabilities)

- **Data-quality issue with `xlt()`:** `xlt()` is used to build JSON values (`xlt($dataRecordProvider['role_title'])` and `xlt("Unknown")`). `xlt()` HTML-escapes its output, so API consumers may receive entity-encoded strings. This does not create XSS; output encoding should simply happen at the presentation layer. Use `xl()` for API payloads.
- **Injection:** No injection concerns were found in the new search parameters (`status`, `_id`, `patient`), assuming the shared search-field framework binds values as parameters, as it does elsewhere.

## Summary

There is one high-severity broken access control regression. Patient-context restrictions are no longer enforced for CareTeam reads and searches because the class does not implement `IPatientCompartmentResourceService`. This should be fixed before merging.