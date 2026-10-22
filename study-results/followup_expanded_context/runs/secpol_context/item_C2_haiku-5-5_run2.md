## Security review: `FhirCareTeamService.php`

The most serious issue is a patient-scoping regression that removes access control for CareTeam data. There are also smaller items that need verification.

### Finding 1: Patient binding is silently dropped, allowing cross-patient CareTeam access

- **Location:** `FhirCareTeamService.php`, class declaration (`implements IResourceUSCIGProfileService` instead of `IPatientCompartmentResourceService`), the removed `getOne()` override, and `searchForOpenEMRRecords()`. The base-class code is in `FhirServiceBase.php`.
- **OWASP category:** A01:2021 Broken Access Control (IDOR / missing function-level and object-level authorization)
- **Problem:** The patient-binding mechanism works as follows:
  1. `FhirServiceBase::createOpenEMRSearchParameters()` adds the `puuidBind` filter only when `$this instanceof IPatientCompartmentResourceService`. This class no longer implements that interface, so the filter is never added.
  2. `FhirServiceBase::getAll()` calls `$this->searchForOpenEMRRecords($oeSearchParameters)` with only one argument. The `$puuidBind` value is never passed to the override, even though the override accepts it. The `puuidBind` argument to `searchForOpenEMRRecords()` is therefore dead code.
  3. The removed `getOne()` override previously delegated to `$this->careTeamService->getOne($fhirResourceId, $puuidBind)`, which enforced the patient bind in the data layer. The inherited `FhirServiceBase::getOne()` relies on the interface check from point 1, so the bind is lost.

  Result: a request scoped to one patient (for example, a portal `Patient/{puuid}/CareTeam` read or search, where `$puuidBind` is set) returns CareTeam records for all patients. A direct `CareTeam/{id}` read for a record belonging to another patient is also not blocked. CareTeam data (care team membership, roles, facilities) is patient-linked health information, so this exposes PHI across patient boundaries.
- **Severity:** High (Critical if the patient-portal FHIR API is enabled in production). This is a regression introduced by this change.
- **Recommended fix:** Make the class implement `IPatientCompartmentResourceService` (and add the `getPatientContextSearchField()` contract that the interface requires). Alternatively, restore the `getOne()` override and pass `$puuidBind` explicitly through `getAll()` into `searchForOpenEMRRecords()` and then to `CareTeamService`. Add tests that confirm a patient-bound request cannot read another patient's CareTeam by ID or by list.

### Finding 2: Changed flag on `CareTeamService::getAll()` may alter the data returned

- **Location:** `FhirCareTeamService.php`, `searchForOpenEMRRecords()`: `getAll($openEMRSearchParameters, false, $puuidBind)` changed to `getAll($openEMRSearchParameters, true, $puuidBind)`.
- **OWASP category:** A04:2021 Insecure Design (unverified behavior change). Potential A01 impact if the flag controls filtering.
- **Problem:** The diff does not show what the second parameter of `CareTeamService::getAll()` does. If it toggles a FHIR-specific mapping, a data-scope filter, or inclusion of non-public or inactive records, this change could expose extra fields or records. The reviewer should confirm the flag's meaning from `CareTeamService.php`.
- **Severity:** Low to Medium, pending verification.

### Finding 3: Unescaped and unvalidated values flow into the FHIR output (low risk)

- **Location:** `parseOpenEMRRecord()`: `lookup_code_descriptions(...)`, `xlt($dataRecordProvider['role_title'])`, and the `explode(':')` code parsing.
- **OWASP category:** A03:2021 Injection (output encoding), low likelihood.
- **Problem:** Display strings and codes come from the database and are placed into a `json_encode` FHIR resource. JSON encoding prevents HTML/script injection as long as the output is served as `application/json` and not rendered as HTML. `xlt()` returns a translation and does not HTML-escape. Confirm that no consumer renders these fields into HTML without escaping. There is no SQL injection here because the values are not concatenated into queries in this file.
- **Severity:** Informational / Low.

### Items reviewed with no issue found

- **Status handling:** `status` is checked against a whitelist (`CARE_TEAM_STATII`) with a safe default of `active`. This is correct.
- **Search parameter definitions:** The `status`, `_id`, and `patient` parameters map to fixed service field names, not raw user input.
- **Provenance:** The new `createProvenanceResource()` type-checks its input and throws on a wrong type.
- **Logging:** The `SystemLogger` calls in `FhirServiceBase` record only parameter names, not values, so no PHI is logged.
- **Pre-existing, in `FhirServiceBase`:** `getOne()` uses `isset($puuidBind)` while `createOpenEMRSearchParameters()` uses `!empty($puuidBind)`. This inconsistency with an empty-string bind is the same root-cause area as Finding 1 and should be cleaned up alongside that fix.

### Summary

| # | Location | Category | Severity |
|---|----------|----------|----------|
| 1 | Interface and `getOne()`/`searchForOpenEMRRecords()` | A01 Broken Access Control | High (regression) |
| 2 | `searchForOpenEMRRecords()` flag change | A04 / possible A01 | Low–Medium (verify) |
| 3 | Output of DB-derived display and code values | A03 (output encoding) | Informational |

**Recommendation:** Do not merge until Finding 1 is fixed and covered by a test. Verify Finding 2 against `CareTeamService::getAll()`.