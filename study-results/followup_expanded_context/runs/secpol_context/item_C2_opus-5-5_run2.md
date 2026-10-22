# Security Review: `FhirCareTeamService.php`

## Finding 1: Patient-context restriction removed, so one patient can read others' care teams

**Location:**
- `src/Services/FHIR/FhirCareTeamService.php`, the class declaration (`class FhirCareTeamService extends FhirServiceBase implements IResourceUSCIGProfileService`)
- The removal of the overridden `getOne($fhirResourceId, $puuidBind = null)`
- The `searchForOpenEMRRecords($openEMRSearchParameters, $puuidBind = null)` method

**OWASP category:** A01:2021 – Broken Access Control (Insecure Direct Object Reference)

**Severity:** High. This exposes PHI across patients, a HIPAA-relevant data breach.

**Problem:**

Before this change, `getOne()` passed `$puuidBind` directly to `CareTeamService::getOne()`. That limited results to the logged-in patient in patient-bound contexts, such as patient-portal or SMART `patient/*.read` scopes.

The PR deletes that override and now relies on `FhirServiceBase`. The base class only enforces the patient binding when the service implements `IPatientCompartmentResourceService`:

```php
// FhirServiceBase::getOne
if (isset($puuidBind) && $this instanceof IPatientCompartmentResourceService) { ... }

// FhirServiceBase::createOpenEMRSearchParameters
if (!empty($puuidBind) && $this instanceof IPatientCompartmentResourceService) {
    $oeSearchParameters[$patientField->getName()] = ...;
}
```

`FhirCareTeamService` defines `getPatientContextSearchField()` but does not declare `implements IPatientCompartmentResourceService`. As a result, both checks are silently skipped.

In addition, `FhirServiceBase::getAll()` calls `$this->searchForOpenEMRRecords($oeSearchParameters)` without the `$puuidBind` argument. The `$puuidBind` parameter on `FhirCareTeamService::searchForOpenEMRRecords` is therefore always `null`. Nothing passes the binding down to `CareTeamService::getAll()` either.

**Impact:** A user authenticated in patient context can retrieve any patient's care team. The data includes providers, facilities, roles and the patient UUID. Two request patterns work:
- `GET /fhir/CareTeam/{any-uuid}`
- `GET /fhir/CareTeam?patient={other-puuid}`, or a search with no filter at all

**Fix:**
- Declare `implements IResourceUSCIGProfileService, IPatientCompartmentResourceService` so the base class applies the patient filter in `getOne()` and `getAll()`.
- Add a regression test confirming that a patient-bound token cannot read another patient's CareTeam, either by `_id` or by `patient=` search.

## Finding 2 (pre-existing, in relied-upon code): base class does not forward `$puuidBind`

**Location:** `FhirServiceBase::getAll()`, which calls `searchForOpenEMRRecords($oeSearchParameters)`, and the abstract signature that omits `$puuidBind`.

**OWASP category:** A04:2021 – Insecure Design (contributes to A01)

**Severity:** Medium

**Problem:** Patient-scoping depends entirely on each subclass remembering to implement the `IPatientCompartmentResourceService` marker interface. There is no defense in depth:
- `$puuidBind` is never passed to the data layer.
- A subclass that forgets the interface fails open. It returns all patients' data with no error or log entry.

Finding 1 is a direct result of this design.

**Fix:** Pick one or more of the following:
- Fail closed: if `$puuidBind` is set and the service is not a patient-compartment service, reject the request or log it, unless the resource is explicitly marked as non-patient data.
- Forward `$puuidBind` to `searchForOpenEMRRecords`.
- Add an audit log entry when patient-bound requests are served.

## Minor observation (not a vulnerability)

`xlt()` HTML-escapes its output. It is used here to build values that are JSON-encoded into FHIR resources. This can produce double-encoded display strings. `xl()` is the appropriate function for non-HTML output. It is a data-correctness issue, not a security flaw.

## Summary

| # | Location | OWASP | Severity |
|---|----------|-------|----------|
| 1 | `FhirCareTeamService` missing `IPatientCompartmentResourceService`; `getOne` override removed | A01 Broken Access Control | **High** |
| 2 | `FhirServiceBase::getAll` / `createOpenEMRSearchParameters` fail open | A04 Insecure Design | Medium |

**Recommendation:** Do not merge until Finding 1 is fixed and covered by a test.