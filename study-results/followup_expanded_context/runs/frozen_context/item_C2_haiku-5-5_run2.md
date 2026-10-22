## Review: FhirCareTeamService changes

The PR adds US Core CareTeam support (status, role coding, `onBehalfOf`, search parameters, provenance). I found several correctness and maintainability issues, plus a few things I could not verify from the diff alone.

### Issues

**1. Comment contradicts code: "first facility" vs `end()` (Medium, correctness/readability)**
In the provider loop, the comment says "we are only going to grab the first facility for now", but `end($dataRecordProviderList)` returns the **last** element. Either the code or the comment is wrong. If the query orders rows deterministically, this choice silently determines which facility/role is emitted, so it should be explicit and tested.

**2. Inconsistent SNOMED handling between provider and facility roles (Medium, correctness)**
The facility branch checks `$codeParts[0] === "SNOMED-CT"` and assigns `SNOMED_CT` as the system. The provider branch always assigns `NUCC_PROVIDER`, even when the prefix is `SNOMED-CT:`. A SNOMED-prefixed provider role code would be emitted under the wrong code system, producing an invalid coding.

**3. Possible undefined-index notices on row fields (Medium, reliability)**
The code reads `$dataRecord['status']`, `['puuid']`, `['providers']`, `['facilities']`, `['role_code']`, `['role_title']`, `['facility_uuid']`, `['provider_uuid']`, `['uuid']`, and `['facility_taxonomy']` directly. Nothing in the diff shows that the underlying `CareTeamService` query returns all of these keys in every case. If any are missing, PHP emits notices and, in a JSON/FHIR response, these can corrupt output. Use `?? null` or verify the query shape.

**4. Loose `array_search` for status validation (Low, correctness)**
`array_search($dataRecord['status'], self::CARE_TEAM_STATII) !== false` uses loose comparison. Use `in_array(..., true)` for strict matching. Since the value is user/DB data, strictness matters. `in_array` also reads more clearly than `array_search(...) !== false`.

**5. Unchecked `createRelativeReference` inputs (Medium, reliability)**
`provider_uuid`, `uuid`, and `puuid` are passed straight into `UtilsService::createRelativeReference`. A null or empty UUID (for example, a provider row with no matching practitioner UUID) produces a malformed reference like `Practitioner/`, which is an invalid FHIR resource. Null members should be filtered out or raised as errors.

**6. Behaviour change in `searchForOpenEMRRecords`: `false` → `true` (Medium, needs verification)**
The second argument to `$careTeamService->getAll()` changed from `false` to `true` with no explanation in the diff. This is an undocumented behaviour change that could affect what data is returned, or whether the provider/facility arrays are populated. It needs a justification in the PR description or a comment, and should be verified against `CareTeamService::getAll`'s signature.

**7. `getOne` override removed without replacement rationale (Low-Medium, behaviour)**
The custom `getOne` used `careTeamService->getOne($id, $puuidBind)` directly. It is now replaced by the base-class implementation, which goes through the `_id` search path and `getAll`. This changes the lookup path, the patient-binding behaviour, and error handling. It may be fine, but the PR should state it and tests should cover patient-bound `getOne`.

**8. `createProvenanceResource` now throws on wrong type (Low, reliability)**
Throwing `\BadMethodCallException` is a stricter contract than the other FHIR services. `FhirServiceBase::getAll` calls this method with whatever `parseOpenEMRRecord` returned, so this should be fine, but the existence of `createProvenanceForDomainResource` on `FhirProvenanceService` also needs to be confirmed; the diff does not show it.

**9. Duplicated role-building code (Low, maintainability)**
The provider `if` and `else` branches and the facility block each construct `FHIRCodeableConcept` and `FHIRCoding` with near-identical logic. Extracting a helper (for example `buildRoleCodeableConcept($code, $display, $system)`) would reduce the chance of the inconsistencies in items 1 and 2 recurring.

**10. Per-row global lookups (Low, performance/coupling)**
`lookup_code_descriptions()` and `xlt()` are called inside the per-row mapping, and the mapper depends on global functions. Descriptions could be batched or cached, and the mapper would be easier to test if this were injected.

**11. Minor style and consistency (Low)**
- `const USCGI_PROFILE_URI` is public and not `private const`, unlike the other constants. Its name also uses "USCGI" where the rest of the codebase would typically say "USCG" or "USCORE".
- The `CARE_TEAM_STATII` declaration has an oddly placed comma and inconsistent line breaks.
- Multiple blank lines before `if ($encode)` and around `setSubject`.
- The removed `getOne` docblock was useful; the new base-class behaviour is not documented here.
- `getPatientContextSearchField()` is defined both as a public method and inline in `loadSearchParameters`. The method is fine, but the instance is built twice per construction.

### Things I could not verify from the diff
- That `UtilsService`, `FhirCodeSystemUris`, and `FhirProvenanceService::createProvenanceForDomainResource` exist and are in the `OpenEMR\Services\FHIR` namespace (the file has no `use` statements for them).
- That `careteam_status` and the `uuid`/`puuid` service fields are supported by `CareTeamService`.
- That `IResourceUSCIGProfileService` exists with `getProfileURIs()`.

### Summary
Highest priority: items 1 and 2 (the comment/code mismatch and the SNOMED mis-coding), item 5 (malformed references from null UUIDs), and item 6 (the unexplained `getAll` flag change). Items 3 and 4 are straightforward hardening. The rest are maintainability improvements. I would request changes before merging, plus tests covering a provider with multiple facilities, a SNOMED-prefixed role code, and a patient-bound `getOne`.