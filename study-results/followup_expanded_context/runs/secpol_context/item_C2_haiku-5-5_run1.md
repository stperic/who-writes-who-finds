## Security review: `FhirCareTeamService.php`

The most serious problem is a patient-scoping gap that exposes CareTeam data across patients. The other findings are lower risk.

### Finding 1: Patient-context binding is not enforced (cross-patient data exposure)

- **Location:** `FhirCareTeamService` class declaration (`implements IResourceUSCIGProfileService`, no `IPatientCompartmentResourceService`); `loadSearchParameters()`; `getPatientContextSearchField()`. Relies on `FhirServiceBase::getOne()`, `getAll()`, and `createOpenEMRSearchParameters()`.
- **OWASP category:** A01:2021 Broken Access Control (also A04 Insecure Design)
- **Problem:** The base class only applies the patient-bind filter when `$this instanceof IPatientCompartmentResourceService`. This class adds `getPatientContextSearchField()` and a `patient` search parameter, but never implements `IPatientCompartmentResourceService`, so the check is false. As a result:
  - `createOpenEMRSearchParameters()` never injects the `$puuidBind` restriction.
  - `getOne($id, $puuidBind)` only uses `_id`, so a patient-bound caller (for example, a patient portal user) can read any CareTeam by ID.
  - Also, `FhirServiceBase::getAll()` calls `searchForOpenEMRRecords($oeSearchParameters)` without `$puuidBind`, and this class's `searchForOpenEMRRecords()` passes that null value to `careTeamService->getAll(...)`. The bind is therefore dropped at every layer for this resource, so a portal caller can also use `patient=<other puuid>` to list other patients' care teams.
  - The removal of the local `getOne()` override, which previously passed `$puuidBind` to the data service, makes this worse. Before this change, the data service received the bind, so it had at least one enforcement point.
- **Severity:** High. This exposes PHI (care team membership tied to specific patients) across patient boundaries.
- **Fix:** Declare `implements IResourceUSCIGProfileService, IPatientCompartmentResourceService`. Also pass `$puuidBind` through `getAll()` to `searchForOpenEMRRecords()` and enforce it in the data service, rather than relying on the compartment interface alone. Add tests that a bound caller cannot read another patient's CareTeam by `_id` or `patient=`.

### Finding 2: Unexplained change to the data-service query mode

- **Location:** `searchForOpenEMRRecords()`: `$this->careTeamService->getAll($openEMRSearchParameters, false, $puuidBind)` changed to `true`.
- **OWASP category:** A04 Insecure Design (integrity of access filtering)
- **Problem:** The second argument's meaning is not visible in this diff. If it selects AND versus OR combination of filters, or changes how the patient restriction is combined, this change can broaden results beyond what callers requested. The change is not explained in the PR and is not covered by any visible test.
- **Severity:** Medium (needs verification against `CareTeamService::getAll` signature). Could be High if it weakens filtering.
- **Fix:** Confirm the parameter's meaning, document why the change is needed, and add tests for multi-parameter searches.

### Finding 3: Loose comparison on status validation

- **Location:** `parseOpenEMRRecord()`: `array_search($dataRecord['status'], self::CARE_TEAM_STATII) !== false`
- **OWASP category:** A03 Injection (input validation, weak form). Low practical impact here.
- **Problem:** `array_search` uses loose comparison by default. Values that compare loosely to a status string can match. The impact is limited because the result is only echoed into FHIR output, but it is a validation weakness.
- **Severity:** Low.
- **Fix:** Use `in_array($status, self::CARE_TEAM_STATII, true)`.

### Finding 4: Unchecked empty provider list

- **Location:** `foreach ($dataRecord['providers'] as $dataRecordProviderList)` with `$dataRecordProvider = end($dataRecordProviderList);`
- **OWASP category:** A04 Insecure Design (error handling)
- **Problem:** If a list is empty, `end()` returns `false`. The following `$dataRecordProvider['role_code']` and `$dataRecordProvider['provider_uuid']` accesses then produce warnings and may emit a participant with a null `Practitioner` reference. This is a robustness issue, not an exploit path, but it can produce malformed or misleading records.
- **Severity:** Low.
- **Fix:** Skip empty lists before accessing elements.

### Finding 5: Output encoding relies on `xlt()` for display strings

- **Location:** `xlt($dataRecordProvider['role_title'])`, `xlt($dataRecordFacility...)` and `setDisplay(...)` calls.
- **OWASP category:** A03 Injection (XSS, low risk)
- **Problem:** `xlt()` is a translation helper and is not an HTML escaper. The output is serialized as JSON, so there is no direct XSS here. However, if FHIR JSON is ever rendered into HTML without escaping, role titles from the database could be a vector. This is a defense-in-depth note.
- **Severity:** Informational / Low.

### Finding 6: Dead or unverified dependencies used by new code

- **Location:** `lookup_code_descriptions(...)` calls and the `FhirProvenanceService` instantiation.
- **OWASP category:** A06 Vulnerable and Outdated Components (verification gap)
- **Problem:** The diff does not show whether `lookup_code_descriptions()` uses parameterized SQL when the code value comes from stored data. It should be checked for injection, even though the input is currently DB-sourced.
- **Severity:** Informational. Verify.

### Summary

| # | Location | Category | Severity |
|---|---|---|---|
| 1 | Class declaration / binding logic | A01 Broken Access Control | High |
| 2 | `searchForOpenEMRRecords` query mode flag | A04 Insecure Design | Medium (verify) |
| 3 | `parseOpenEMRRecord` status check | A03 (validation) | Low |
| 4 | Provider loop with `end()` | A04 (error handling) | Low |
| 5 | `xlt()` in display strings | A03 (XSS, defense in depth) | Informational |
| 6 | `lookup_code_descriptions` | A06 / verify | Informational |

**Recommendation:** Do not merge until Finding 1 is fixed and covered by a test. Verify Finding 2 before merge.