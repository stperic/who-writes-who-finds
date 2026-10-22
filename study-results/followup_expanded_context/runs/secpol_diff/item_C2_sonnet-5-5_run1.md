## Security review: `FhirCareTeamService.php`

**Result: no exploitable vulnerabilities found in this diff.** I have a few low-severity notes and one thing to verify.

### What I checked

- **Injection (A03):** The new search parameters (`patient`, `status`, `_id`) are declared through `FhirSearchParameterDefinition`, `SearchFieldType` and `ServiceField`. Values go through the framework's search layer, and the diff builds no SQL or string queries. No injection is introduced here. The `lookup_code_descriptions()` calls take DB-stored codes. I couldn't see that function's body, so I'm assuming it uses parameterized queries.
- **Broken access control (A01):**
  - The `getOne()` override is removed, so the parent `FhirServiceBase::getOne()` now handles lookups. That path goes through `searchForOpenEMRRecords($params, $puuidBind)` and still passes the patient binding.
  - `searchForOpenEMRRecords()` changes the second `getAll()` argument from `false` to `true`. I assume this is the `$isAndCondition` flag. If so, this is a security improvement. With OR semantics, a combined `patient` and `status` search, or a patient bind plus other filters, could return records outside the intended patient.
  - **Verify:** confirm that `CareTeamService::getAll()` applies `$puuidBind` as a mandatory AND filter and that `_id` and `patient` resolve to the right columns. Add a test that a patient-scoped token cannot read another patient's CareTeam through `_id`.
- **Output and encoding (A03/XSS):** Output is built as typed FHIR objects and serialized with `json_encode`, so there is no XSS sink in this code.
- **Logging, SSRF, crypto, components, integrity:** The diff does not touch any of these. The new Provenance method only wraps an existing service and type-checks its input.

### Low-severity and informational notes

1. **Loose `array_search()` on status (`parseOpenEMRRecord`), A04/A08, Low.**
   - `array_search($dataRecord['status'], self::CARE_TEAM_STATII) !== false` uses loose comparison. On PHP < 8, a value like `0` can match `"active"` and be emitted as the status.
   - A missing `status` key also raises an undefined-index notice.
   - Use `in_array(..., true)` and `$dataRecord['status'] ?? null`.
2. **`xlt()` applied to stored data (`role_title`), Low (correctness).**
   - `xlt()` HTML-escapes its output, so the FHIR JSON would carry HTML entities, for example `&amp;`. This is not an XSS risk, since it over-escapes rather than under-escapes, but it is the wrong function for a JSON API. Use `xl()` or the raw value.
   - It also tries to translate DB data as if it were a UI string.
3. **Unchecked `end()` result (A04, Low/robustness).**
   - If `$dataRecordProviderList` is empty, `end()` returns `false`. The code then indexes into `false` and emits a participant with a null member reference.
   - Guard against this, since malformed references in clinical data are an integrity concern.
4. **Practitioner and organization disclosure (A01, Informational).** The CareTeam now exposes practitioner references, facility references and role codes. Confirm that the SMART scopes enforced for this resource (`patient/CareTeam.read`, `user/CareTeam.read`) gate this, and that the new US Core profile registration doesn't bypass the scope checks.
5. **Unresolved TODO on `facility_taxonomy` column size.** If the column truncates codes, the output could carry wrong code values. This is a data-integrity issue only.

No blocking security issues. I recommend fixing item 1 and verifying the `puuidBind` behavior before merge.