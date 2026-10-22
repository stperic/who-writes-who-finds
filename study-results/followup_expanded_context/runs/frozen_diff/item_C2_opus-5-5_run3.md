# PR Review: `FhirCareTeamService.php`

## High

**1. `xlt()` used for JSON/FHIR output (HTML escaping corrupts data)**
- **Location:** provider role block (`xlt($dataRecordProvider['role_title'])`, `xlt("Unknown")`) and facility block (`xlt("Unknown")`)
- **Problem:** In OpenEMR, `xlt()` translates the string and then HTML-escapes it. This resource is serialized to JSON, not rendered as HTML.
  - Titles containing `&`, `<`, `'` and similar characters will be emitted as entities, e.g. `&amp;`.
  - Escaping belongs in the presentation layer, not the API payload.
- **Also:** Translating `Coding.display` is semantically wrong.
  - The display for `data-absent-reason#unknown` should be the code system's display ("Unknown"), not a locale-dependent string.
  - Running a DB value (`role_title`) through the translation table is also questionable.
- **Fix:** Use the plain string for code-system displays. If translation is truly wanted, use `xl()`, which does not escape.

**2. Comment says "first facility" but code takes the last**
- **Location:** `$dataRecordProvider = end($dataRecordProviderList);`
- **Problem:** `end()` returns the last element, contradicting the comment. If `$dataRecordProviderList` is empty or not an array, `end()` returns `false`. The following `$dataRecordProvider['role_code']` and `['provider_uuid']` accesses then silently yield null. The result is a participant with an invalid `Practitioner/` reference.
- **Fix:**
  - Use `reset()`, or `$list[0] ?? null`, or fix the comment to match the intended behavior.
  - Skip the participant (or log) when no provider row or `provider_uuid` exists.

**3. `lookup_code_descriptions()` dependency**
- **Location:** both role blocks
- **Problem:** This is a global function from `custom/code_types.inc.php`. Inside a namespaced service used by the REST/FHIR API, nothing here guarantees that file is loaded. If it isn't, the call is a fatal "undefined function" error at runtime.
- **Fix:** Ensure the include is present in the API bootstrap, or call through a service such as `CodeTypesService`, which is preferable and testable.

## Medium

**4. Status search field vs. record key mismatch**
- **Location:** `'status' => new FhirSearchParameterDefinition('status', SearchFieldType::TOKEN, ['careteam_status'])` vs. `$dataRecord['status']`
- **Problem:** The search maps to `careteam_status`, while parsing reads `status`. Please confirm `CareTeamService::getAll` exposes both names (or a column aliased appropriately). Otherwise either status search or status output is broken.
- **Additional issues:**
  - `$dataRecord['status']` is accessed without `??`, which produces an undefined index notice if the key is absent.
  - `array_search` is non-strict; use `in_array($status, self::CARE_TEAM_STATII, true)`.

**5. Behavior change in `searchForOpenEMRRecords`**
- **Location:** `getAll($openEMRSearchParameters, true, $puuidBind)`
- **Problem:** Flipping `isAndCondition` from `false` to `true` changes semantics for all callers. It is probably correct for FHIR (search parameters AND together), but it isn't mentioned or tested.
- **Fix:** Add a test, or a comment explaining why.

**6. Removal of `getOne` override**
- **Problem:** This relies on the base class implementing `getOne` via `_id` search, and still enforcing `$puuidBind` (patient-scope access control). Please verify that patient-bound tokens cannot read other patients' care teams via `/CareTeam/{id}`. This is a security-relevant regression risk.

**7. No null guards on arrays and references**
- **Location:** `foreach ($dataRecord['providers'] ...)`, `foreach ($dataRecord['facilities'] ...)`, and `createRelativeReference("Patient", $dataRecord['puuid'])`
- **Problem:** Missing or null values produce warnings and invalid references. US Core requires `subject`, so an empty `puuid` yields a non-conformant resource.
- **Fix:** Use `?? []` and validate required fields.

## Low / Maintainability

8. **`meta.lastUpdated` is always "now":** `versionId` is hard-coded to `1`. This makes caching and `_lastUpdated` meaningless. It was pre-existing, but it is worth a TODO now that `FHIRMeta` is being touched.

9. **Duplicated role-building logic:** The provider and facility blocks construct the CodeableConcept and data-absent-reason coding in near-identical code. Extract a helper such as `createRoleCodeableConcept($taxonomy, $fallbackTitle)`.

10. **Facility system detection is fragile:** The code assumes a prefix of exactly `"SNOMED-CT"` and treats everything else as NUCC. Other prefixes (e.g. `SNOMED:`) would get the wrong system. The unresolved TODO about column size also shouldn't be merged with personal @-mentions; open an issue instead.

11. **Wrong exception type in `createProvenanceResource`:** `BadMethodCallException` should be `InvalidArgumentException`. The message "should be correct instance class" is also unhelpful; name the expected type.

12. **Naming and style:**
    - `USCGI_PROFILE_URI` is a typo for USCIG, matching the interface name `IResourceUSCIGProfileService`.
    - The constant lacks a visibility modifier, while the other constants are `private`.
    - `CARE_TEAM_STATII` is an odd name; use `CARE_TEAM_STATUSES`.
    - There are multiple stray blank lines (after the subject and before `if ($encode)`).

13. **Misleading comment:** "US Core only allows onBehalfOf to be populated if participant is a practitioner." The code is correct (members are Practitioners), but the comment reads like a guard that isn't actually checked.

## Summary
The direction is good: US Core profile, search parameters, roles, and provenance. Before merging, please:
- remove HTML escaping (`xlt`) from the API output;
- resolve the `end()`/"first" mismatch and add empty guards;
- ensure `lookup_code_descriptions` is available in the API context;
- verify the status field mapping and the patient-binding behavior after removing `getOne`.