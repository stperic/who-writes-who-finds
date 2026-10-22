## Security Review

### 1. Broken Access Control — Patient-scoping (puuidBind) is silently dropped for CareTeam lookups
**Location:** `src/Services/FHIR/FhirCareTeamService.php` — class declaration (`implements IResourceUSCIGProfileService`) and removal of the `getOne()` override; also `FhirServiceBase::getAll()` / `createOpenEMRSearchParameters()`.

**Problem:**
The previous version of this class explicitly overrode `getOne()`:

```php
public function getOne($fhirResourceId, $puuidBind = null)
{
    $processingResult = $this->careTeamService->getOne($fhirResourceId, $puuidBind);
    ...
}
```

which forwarded `$puuidBind` directly to the data-access layer, guaranteeing that a patient-context-bound request (e.g. a SMART-on-FHIR patient-launched app) could only retrieve its own CareTeam resource.

This override has been **deleted**. The class now falls back to `FhirServiceBase::getOne()`, which only applies the `puuidBind` restriction when:

```php
if (isset($puuidBind) && $this instanceof IPatientCompartmentResourceService) { ... }
```

`FhirCareTeamService` is declared as `implements IResourceUSCIGProfileService` only — it does **not** implement `IPatientCompartmentResourceService`, even though it defines `getPatientContextSearchField()` and registers a `patient` search parameter (suggesting this was the intent). As a result:

- `createOpenEMRSearchParameters()` will never add the patient-restriction search field.
- `FhirServiceBase::getAll()` never forwards `$puuidBind` to `searchForOpenEMRRecords()` at all, so even the `$puuidBind` parameter added to the new `searchForOpenEMRRecords($openEMRSearchParameters, $puuidBind = null)` signature is effectively dead code — it will always be `null` when invoked through the normal `getOne()`/`getAll()` flow.

Net effect: a request scoped to a specific patient (e.g. via `_id` lookup or any patient-bound FHIR call) can return another patient's CareTeam resource (and PHI contained within — practitioners, roles, organizations). This is a classic IDOR/cross-patient data exposure.

**Severity:** **Critical** — unauthorized disclosure of PHI across patient boundaries (HIPAA-relevant), directly maps to OWASP A01:2021 Broken Access Control.

---

### 2. Insecure Design / Security Misconfiguration — Unexplained behavior change in `searchForOpenEMRRecords`
**Location:**
```php
- return $this->careTeamService->getAll($openEMRSearchParameters, false, $puuidBind);
+ return $this->careTeamService->getAll($openEMRSearchParameters, true, $puuidBind);
```

**Problem:** The second positional boolean argument to `CareTeamService::getAll()` was flipped from `false` to `true`. Its semantics aren't visible in this diff (likely something like "strict AND" matching, "include inactive," or "respect facility restrictions"). Combined with issue #1 above (where `$puuidBind` is effectively never populated), any change that broadens result filtering here compounds the access-control risk. This needs to be verified against `CareTeamService::getAll()`'s implementation to ensure it does not weaken row-level restrictions (e.g., active user/facility scoping) that existed previously.

**Severity:** Medium (pending verification) — flag for review; could escalate the severity of #1 if it loosens filtering further.

---

### 3. Potential Injection / unvalidated data rendered into FHIR output
**Location:**
```php
$description = lookup_code_descriptions($dataRecordProvider['role_code']);
...
$roleCoding->setDisplay($description);
```
and the analogous facility_taxonomy block.

**Problem:** `lookup_code_descriptions()` is called with data pulled from the care-team provider/facility records and its return value is placed directly into the FHIR `display` field without sanitization or escaping (unlike the fallback branch, which calls `xlt()`). If `lookup_code_descriptions()` performs raw SQL concatenation internally (not shown/verifiable here) this could be a SQL injection vector; if the returned text can contain HTML/script and is later rendered by a FHIR-consuming web client without proper escaping, it could enable stored XSS downstream. This routine is outside this diff but is newly exercised by this change and should be audited.

**Severity:** Low–Medium (depends on `lookup_code_descriptions()` implementation — flag for follow-up, not confirmed exploitable from this diff alone).

---

### 4. Minor inconsistency: data-absent-reason / error handling
**Location:** facility role-building block, `TODO` comment:
```php
// TODO: @adunsulag check with @brady.miller @sjpadgett on how facility_taxonomy has a limit on the column size.
```
**Problem:** Not a direct vulnerability, but truncated/unexpected taxonomy codes being silently `explode()`'d and used to select a coding `system` (SNOMED-CT vs NUCC) without validation could result in mislabeled clinical codes being returned via the FHIR API (data integrity concern, not exploitable security bug). Logged here as a data-integrity note rather than a hard vulnerability.

**Severity:** Informational.

---

### No issues found in:
- Use of parameterized `FhirSearchParameterDefinition`/`ServiceField` definitions for `patient`, `status`, `_id` search params — these use typed search fields (TOKEN/REFERENCE/UUID) rather than raw SQL, which is the correct pattern assuming `FHIRSearchFieldFactory` and `ServiceField` properly parameterize queries downstream.
- `FHIRId`/`FHIRMeta` usage — standard library objects, no issues.
- Status whitelist check (`array_search($dataRecord['status'], self::CARE_TEAM_STATII)`) is a good example of allow-listing untrusted/stored data before use.

---

## Summary
The standout, serious issue is **#1: loss of patient-context enforcement on CareTeam resource retrieval** caused by removing the `getOne()` override and not implementing `IPatientCompartmentResourceService`, combined with `FhirServiceBase::getAll()` never forwarding `$puuidBind` to `searchForOpenEMRRecords()`. This should block merge until patient-scoping is restored (either implement `IPatientCompartmentResourceService` and confirm `createOpenEMRSearchParameters()` enforces the patient bind, or reinstate an explicit `getOne()` override that passes `$puuidBind` through to `CareTeamService`). The `true`/`false` flag change and the unescaped `lookup_code_descriptions()` output should also be verified before merge.