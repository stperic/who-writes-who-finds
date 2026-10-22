## Security review of the `FhirCareTeamService` change

### 1. Patient-compartment access control is not enforced (High)

- **Location:** `FhirCareTeamService` class declaration, `getPatientContextSearchField()`, and the removed `getOne()` override. These interact with `FhirServiceBase::getOne()`, `getAll()` and `createOpenEMRSearchParameters()`.
- **OWASP category:** A01:2021 Broken Access Control.
- **Problem:**
  - The class now declares `getPatientContextSearchField()` but only implements `IResourceUSCIGProfileService`. It does not implement `IPatientCompartmentResourceService`.
  - `FhirServiceBase` only restricts results to the bound patient when `$this instanceof IPatientCompartmentResourceService`. This check appears in both `createOpenEMRSearchParameters()` and `getOne()`.
  - For this service, the check is always false, so the `$puuidBind` restriction is silently skipped.
  - The PR also deletes the custom `getOne()` that explicitly passed `$puuidBind` to `CareTeamService::getOne()`. The base `getOne()` is now used, and it drops the binding.
  - Base `getAll()` also calls `searchForOpenEMRRecords($oeSearchParameters)` without `$puuidBind`, so the override's `$puuidBind` parameter is never populated.
  - Result: a patient-scoped token (patient portal or `patient/CareTeam.read`) can read any patient's CareTeam through `GET /CareTeam`, `GET /CareTeam/{id}`, or `?patient=<other>`. The care team exposes patient UUIDs, provider and facility relationships, and roles. This is a regression, because the old `getOne()` enforced the binding.
- **Fix:**
  - Declare `implements IPatientCompartmentResourceService`.
  - Make the base class pass `$puuidBind` through, or add a regression test that a bound patient cannot read another patient's CareTeam.

### 2. Possible flipped AND/OR flag in `searchForOpenEMRRecords` (Low to Medium; needs verification)

- **Location:** `searchForOpenEMRRecords()`, where `getAll($params, false, $puuidBind)` became `getAll($params, true, $puuidBind)`.
- **OWASP category:** A01:2021 Broken Access Control / A04:2021 Insecure Design.
- **Problem:** The second argument is probably `$isAndCondition`. The new value `true` is the safer one, because OR-combined filters, including a patient filter, would broaden results. Confirm the semantics and add tests that the patient filter is always AND-ed. This is not a vulnerability introduced by the diff.

### 3. Output encoding applied to data (Low / informational)

- **Location:** `xlt($dataRecordProvider['role_title'])` and `xlt("Unknown")` used in JSON FHIR output.
- **OWASP category:** A03:2021 Injection (data handling).
- **Problem:** `xlt()` translates and HTML-escapes. Using it on stored data in a JSON API causes incorrect double-encoding and translation of user data. It is not directly exploitable, since JSON encoding is applied afterward. Use the raw value for API output and escape at the HTML rendering layer.

### 4. Other observations (no issue)

- The status value is checked against a whitelist.
- References are built with `UtilsService::createRelativeReference`.
- No SQL is built in this diff, and search fields go through the typed definitions.
- `createProvenanceResource` validates its input type.

**Summary:** Issue 1 should block the merge.