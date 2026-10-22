## Security review: `FhirCareTeamService.php`

**Summary:** I found no exploitable vulnerabilities in this diff. The notes below are low-severity or need verification. There is no SQL, command or SSRF sink in the changed code. Search values go through `FhirSearchParameterDefinition` and `ServiceField`, which are the framework's parameterized search path.

### Findings

**1. `xlt()` used on database content in a JSON API response**
- **Location:** `parseOpenEMRRecord`, `$description = xlt($dataRecordProvider['role_title']);`
- **OWASP:** A03 Injection (output encoding), minor
- **Problem:** `xlt()` translates a string and HTML-escapes it for page output. Here it is applied to a database value and placed in a FHIR JSON payload. This is the wrong context. It is not exploitable as XSS because `json_encode` handles JSON escaping and the API returns `application/fhir+json`. However, it can send HTML-entity-encoded text to clients (data corruption), and it passes user-controlled data through the translation lookup. If a consumer renders the value as HTML, relying on this partial escaping is fragile.
- **Severity:** Low / informational
- **Fix:** Don't use `xlt` on stored data. Use `xl()` only for fixed UI strings, such as the `"Unknown"` display, and rely on JSON encoding for output.

**2. Missing-key and loose-comparison handling on `status`**
- **Location:** `array_search($dataRecord['status'], self::CARE_TEAM_STATII) !== false`
- **OWASP:** A04 Insecure Design (robustness)
- **Problem:** The code assumes `status` exists. A missing key raises a notice or warning, which can leak paths if `display_errors` is on. `array_search` is non-strict, so on PHP 7 a value like `0` or `true` matches `"active"`. The value comes from the database, so the impact is small and it fails open to `active`.
- **Severity:** Low
- **Fix:** Use `in_array($dataRecord['status'] ?? null, self::CARE_TEAM_STATII, true)`.

**3. Access control now depends on inherited and unseen code (verify)**
- **Location:** removal of the `getOne($fhirResourceId, $puuidBind)` override; `searchForOpenEMRRecords` now calls `getAll(..., true, $puuidBind)`
- **OWASP:** A01 Broken Access Control
- **Problem:** Single-resource reads now go through `FhirServiceBase::getOne`. Patient-bound reads, such as a patient-context SMART token, are only safe if the base class passes `$puuidBind` into the search and `CareTeamService::getAll` enforces it. Changing the second argument from `false` to `true` appears to switch search conditions from OR to AND. This is a security improvement, because with OR a patient filter could be widened by other criteria. Confirm that the second parameter is `$isAndCondition`. Also confirm that tests cover a patient-scoped token requesting another patient's CareTeam by `_id`.
- **Severity:** Low to Medium, until verified
- **Fix:** Add a regression test for cross-patient access via `_id` and `patient` with a bound token.

**4. Scope and authorization registration is not visible in this diff**
- **OWASP:** A01 Broken Access Control
- **Problem:** The change adds search parameters and a US Core profile. Make sure the `CareTeam` resource scopes, such as `user/CareTeam.read` and `patient/CareTeam.read`, are enforced and registered in the routes and capability statement. This code does not show it.
- **Severity:** Informational

### Not issues
- Provenance creation type-checks its input and throws `BadMethodCallException`.
- References are built with `UtilsService::createRelativeReference` using UUIDs, not raw concatenation.
- No secrets, crypto, deserialization or external requests are introduced.

**Verdict:** Safe to merge after addressing the minor items (1 and 2) and confirming item 3.