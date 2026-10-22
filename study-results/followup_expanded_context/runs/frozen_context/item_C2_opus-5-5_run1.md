# Code Review: `FhirCareTeamService.php`

## Critical

### 1. Patient-bound requests can read any patient's care team
**Location:** removed `getOne()` override; `implements IResourceUSCIGProfileService`

- **Before:** `getOne()` passed `$puuidBind` straight to `CareTeamService::getOne()`, so patient-scoped requests were limited to that patient.
- **After:** the class falls back to `FhirServiceBase::getOne()`. That method only adds the patient restriction when `$this instanceof IPatientCompartmentResourceService`.
- **The gap:** this class implements `IResourceUSCIGProfileService`, not `IPatientCompartmentResourceService`. So in both `getOne()` and `createOpenEMRSearchParameters()`, the `$puuidBind` restriction is silently skipped.
- **Why it doesn't fail safe:** `FhirServiceBase::getAll()` calls `searchForOpenEMRRecords($oeSearchParameters)` without `$puuidBind`. The `$puuidBind` parameter here is therefore always `null`.
- **Impact:** a patient-scoped token (e.g. SMART patient/standalone launch) can call `GET /fhir/CareTeam/{id}` for any UUID. It can also call `GET /fhir/CareTeam` with no `patient` filter and get every patient's care teams. This is a PHI disclosure / authorization bypass.
- **Fix:** add `IPatientCompartmentResourceService` to the `implements` list. `getPatientContextSearchField()` already exists, so it fits that interface. Also add a test covering a patient-bound request that tries to fetch another patient's resource.

## High

### 2. `lookup_code_descriptions()` may not be loaded in the API context
**Location:** provider and facility role mapping

- This is a global function from `library/options.inc.php` / `custom/code_types.inc.php`. Nothing in this class makes sure it is included.
- If the FHIR API bootstrap doesn't load it, every CareTeam read fails with a fatal "undefined function" error.
- **Fix:** verify the include path, or use a namespaced service (e.g. `CodeTypesService`).

### 3. `xlt()` used for data going into JSON output
**Location:** `xlt($dataRecordProvider['role_title'])`, `xlt("Unknown")` (three places)

- `xlt()` translates and then HTML-escapes. That is wrong for JSON, because values like `&amp;` will appear literally in FHIR output.
- `xlt()` on database content (`role_title`) also misuses the translation layer. Arbitrary data should not be treated as translation keys.
- **Fix:** use `xl()` for the constant labels and pass `role_title` through untranslated.

## Medium

### 4. Semantics change in `searchForOpenEMRRecords()`
**Location:** `getAll($openEMRSearchParameters, false, ...)` changed to `getAll(..., true, ...)`

- The second argument (likely `$isAndCondition`) flips from OR to AND semantics for all search fields.
- This is probably intentional, but it is a behavior change that needs confirming and testing.

### 5. Comment contradicts code when choosing a provider/facility row
**Location:** `$dataRecordProvider = end($dataRecordProviderList);`

- The comment says the code grabs the *first* facility, but `end()` returns the *last*.
- **Fix:** use `reset()` or `$list[0]`, or correct the comment.
- `end()` also emits a warning and returns `false` if the entry isn't an array. Either guard for that or document the expected structure.

### 6. Search parameter column may not match the record field
**Location:** `'status' => ... ['careteam_status']` vs `$dataRecord['status']`

- The search parameter maps to `careteam_status`, but the parser reads `$dataRecord['status']`.
- Confirm that `CareTeamService` exposes both names. Otherwise either searching or parsing is broken.

### 7. Undefined index risk
**Location:** `$dataRecord['status']`, `$dataRecord['providers']`, `$dataRecord['facilities']`

- If any of these keys is missing, the code emits notices, and `foreach` on `null` emits warnings.
- **Fix:** use `$dataRecord['status'] ?? null` and `?? []` for the arrays.

## Low

### 8. Non-strict status check
**Location:** `array_search($dataRecord['status'], self::CARE_TEAM_STATII) !== false`

- This uses loose comparison. Prefer `in_array(..., true)` for clarity and strictness.

### 9. Prefix handling for codes
**Location:** facility taxonomy system selection

- Any value not prefixed with `SNOMED-CT` is labeled NUCC, including unknown prefixes.
- Provider role codes are always labeled NUCC, whatever their prefix.
- Consider handling unknown prefixes explicitly, or at least logging them.

### 10. Maintainability nits
- **Naming:** `USCGI_PROFILE_URI` is a typo (should be USCDI / US Core). It is also declared without visibility, unlike the other constants.
- **Formatting:** there are multiple stray blank lines (e.g. after the facilities loop and after the property declaration).
- **TODO:** the TODO in production code tags specific people. Track it in an issue instead.
- **Misplaced comment:** "US Core only allows onBehalfOf to be populated if participant is a practitioner" sits above a facility check. Reword it so it's clear the condition is about the member being a Practitioner.
- **Pre-existing:** `meta.lastUpdated` is always "now" and `versionId` is always `'1'`, so it doesn't reflect actual record changes.

## Summary
The PR shouldn't be merged until **#1** is fixed. It drops patient-scoped access control for CareTeam reads and searches. **#2** and **#3** should also be addressed before merge, and **#4** and **#6** need confirmation.