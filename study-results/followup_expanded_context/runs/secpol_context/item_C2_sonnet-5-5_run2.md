## Security review

### 1. Patient-compartment access control is not enforced for CareTeam (High)

**Location:** `FhirCareTeamService.php`, class declaration, the removed `getOne()` override, and `searchForOpenEMRRecords()`. It interacts with `FhirServiceBase::getOne()`, `createOpenEMRSearchParameters()` and `getAll()`.

**OWASP:** A01:2021 Broken Access Control

**Problem:**
- The PR adds `getPatientContextSearchField()` and a `patient` search parameter, but the class implements only `IResourceUSCIGProfileService`. It does not implement `IPatientCompartmentResourceService`.
- `FhirServiceBase` applies the patient binding only when `$this instanceof IPatientCompartmentResourceService`. This check appears in `createOpenEMRSearchParameters()` (forced `patient` filter from `$puuidBind`) and in `getOne()`.
- The PR also deletes the old `getOne()` override. That override passed `$puuidBind` straight to `CareTeamService::getOne()`. The service now falls back to the base `getOne()`, so the one remaining enforcement path is gone.
- The base `getAll()` calls `$this->searchForOpenEMRRecords($oeSearchParameters)` without `$puuidBind`. The override's `$puuidBind` is therefore always `null`, so the downstream `CareTeamService::getAll(..., $puuidBind)` never receives the binding either.
- Result: a patient-scoped token (patient portal or `patient/CareTeam.read` SMART scope) is no longer restricted to its own patient. The caller can read `CareTeam/{id}` or search `/CareTeam` and get other patients' care teams. Each team exposes the patient reference, the providers, their roles and the facilities. The caller can also pass an arbitrary `patient=` parameter.
- Before this change, `getOne` was bound correctly. This is a regression, and the new search endpoint widens the exposure.

**Fix:**
- Declare `implements IPatientCompartmentResourceService` on `FhirCareTeamService`.
- Make sure the binding reaches the data layer, for example by fixing the base class to pass `$puuidBind` through.
- Add tests that a patient-bound request cannot see another patient's CareTeam, whether by `_id` or by search.

### 2. Lower-severity issues

- **Output encoding of data (Low, A03 Injection / data integrity).** `xlt($dataRecordProvider['role_title'])` is applied to database content. `xlt` is a translation function that HTML-escapes its result. Using it on stored data can corrupt the FHIR output with HTML entities. It also sends arbitrary stored text through the translation lookup. Use the raw value for FHIR output, and let the consumer handle HTML escaping.
- **Unvalidated array keys (Low, A04 Insecure Design).** `$dataRecord['status']`, `$dataRecordProvider['provider_uuid']` and `$dataRecordFacility['uuid']` are accessed without existence checks. `$codeParts[0]` is also read without a check. Malformed or partial records produce PHP notices or warnings, which can leak internal details depending on error display settings, and can yield invalid references.
- **Logging (Low, A09).** The new search and provenance paths add no audit logging for access to care-team data. Base-class logging records only the parameter names.
- **Behavior change to confirm (Informational).** The second argument to `careTeamService->getAll()` changed from `false` to `true`. Verify what that flag controls, such as AND/OR combination of search fields or an authorization-related option. Confirm it does not weaken filtering.

**Summary:** The blocking issue is #1. Do not merge until CareTeam is correctly registered as a patient-compartment resource and the patient binding is verified end to end.