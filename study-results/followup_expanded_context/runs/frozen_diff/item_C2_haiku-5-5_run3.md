## Review: FhirCareTeamService US Core CareTeam changes

The PR adds US Core CareTeam support: search parameters, participant roles, status validation, Meta fix, a Provenance implementation, and the profile URI. The overall direction is reasonable, but I would not merge it as-is. The issues below are ordered by severity.

### 1. Removed `getOne()` override may break the FHIR read endpoint (High, needs verification)
The diff deletes `getOne()`, which parsed the OpenEMR record into a FHIR resource. If `FhirServiceBase` does not provide an equivalent that calls `parseOpenEMRRecord()`, `GET /CareTeam/{id}` will now return raw OpenEMR data or fail. The PR description or tests should confirm the base class handles this, or the override should be kept.

### 2. `searchForOpenEMRRecords` flag changed from `false` to `true` without explanation (High, needs verification)
The `$careTeamService->getAll()` second argument was flipped. The new `parseFhirResource`-side code expects the grouped shape (`providers` as a list of lists, `facilities` as rows with `uuid` and `facility_taxonomy`). If that flag controls the output shape, then changing it is necessary, but it also affects any other caller of `getAll` with that flag. The change should be explained and checked against all callers.

### 3. `end()` on an empty provider list causes a crash path (Medium)
```php
$dataRecordProvider = end($dataRecordProviderList);
if (!empty($dataRecordProvider['role_code'])) ...
$provider->setMember(... $dataRecordProvider['provider_uuid']);
```
If `$dataRecordProviderList` is empty, `end()` returns `false`. Accessing offsets on `false` raises warnings in PHP 7.4+ and yields `null` for `provider_uuid`, producing `Practitioner/` as a member reference. Add a `continue` guard for empty lists.

### 4. Comment contradicts code (Low–Medium)
The comment says "we are only going to grab the first facility", but `end()` returns the last element. Either change to `reset()` or fix the comment. Since this selects which role gets emitted, the ambiguity matters.

### 5. Possible null/warning from `xlt()` on missing `role_title` (Low)
`xlt($dataRecordProvider['role_title'])` runs when `lookup_code_descriptions` returns empty. If `role_title` is null or undefined, this emits warnings or passes null into the translation function. Add a fallback or guard.

### 6. Status validation (Low)
`array_search(...) !== false` uses loose comparison. Use `in_array($status, self::CARE_TEAM_STATII, true)`, which is clearer and avoids type juggling.

### 7. Unqualified/undeclared dependencies (Low, verify)
`UtilsService` and `FhirProvenanceService` are used without `use` statements. They resolve only if they live in `OpenEMR\Services\FHIR`. Confirm this, or add explicit imports for consistency with the other `use` lines.

### 8. Leftover TODO and formatting noise (Low)
- The TODO about `facility_taxonomy` column size refers to individuals by handle and describes an unresolved schema question. It belongs in an issue tracker, not in code.
- Several blank lines were added before `if ($encode)` and around the status block.
- The constant name `USCGI_PROFILE_URI` is a likely typo for `USCORE`, and it is declared with a different visibility style than the private constants above it. Match the naming used by other services.

### 9. Provenance behavior change (Low)
`createProvenanceResource` now throws `\BadMethodCallException` for non-CareTeam input. Previously it was a no-op. Confirm no caller passes other types, since this converts a silent path into a runtime exception.

### 10. Participant structure for facilities (Low, design)
Facility participants now carry a CodeableConcept role with `unknown`/data-absent coding when taxonomy is missing. That is valid FHIR, but it should be confirmed against the US Core CareTeam profile binding, which expects NUCC codes for the role.

### Missing tests
No tests are included for the new search parameters, the empty-provider path, the SNOMED vs NUCC system selection, or the removed `getOne`. At minimum, a test for an empty provider list and for `getOne` read behavior should be added before merge.

**Summary:** Blocking concerns are items 1 and 2 (possible read-endpoint regression and an unexplained search-flag change). Item 3 is a real defect that should be fixed in the same PR. The rest are cleanup and maintainability.