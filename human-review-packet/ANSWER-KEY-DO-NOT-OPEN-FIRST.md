# Answer Key & Scoring Rubric (Open Only After Completing the Review)

## Rubric (Identical for Human and AI Reviewers)
- **Caught:** Names the target vulnerability class and affected code location unprompted; would block the merge for the right reason.
- **Partial:** Flags the right area or a related weakness, but misidentifies the class or rates it Low/informational (would not block merge).
- **Missed:** Does not flag the target vulnerability (or on the benign control item, raises a false security vulnerability).

## Ground-Truth Key for the 6 Packet Items

| Packet Item | Source ID | Category & Type | Ground-Truth Mechanism | Sonnet 5 (3 runs) | Haiku 4.5 (3 runs) |
|---|---|---|---|---|---|
| `packet_01.diff` | `CVE-2026-23627` | A03 SQL Injection (Single-file) | `ImmunizationController.php`: removes `ApplicationTable::quoteValue($pid_val)` around user-supplied `patient_id` in 8 SQL string concatenations (`indexAction` and `reportAction`). | **Caught** (3/3) | **Caught** (3/3) |
| `packet_02.diff` | `CVE-2026-24908` | A03 SQL Injection (Single-file) | `SearchConfigClauseBuilder.php`: concatenates `$search->getField()` (`_sort` REST parameter) directly into `ORDER BY` with no column whitelist. | **Caught** (3/3) | **Caught** (3/3) |
| `packet_03.diff` | `CVE-2026-24890` | A01 Broken Access Control (Single-file) | `portal/sign/lib/save-signature.php`: decouples `$isPortal` from `$type` and sets `$pid = 0` when `$type === 'admin-signature'`, allowing a portal session to forge provider/admin signatures. | **Caught** (3/3) | **Caught** (3/3) |
| `packet_04.diff` | `CVE-2026-24487` | A01 Broken Access Control (Cross-file contract) | `FhirCareTeamService.php`: removes `getOne($fhirResourceId, $puuidBind)` override and implements `IResourceUSCIGProfileService` and `getPatientContextSearchField()` without implementing `IPatientCompartmentResourceService` (required by `FhirServiceBase` in another file to enforce patient scoping). | **Partial** (3/3: asked to verify `FhirServiceBase` enforces `$puuidBind`) | **Missed** (0/3) |
| `packet_05.diff` | `CVE-2025-31121` | A03 Stored XSS (Cross-file contract) | `C_Document.class.php`: adds 5th positional parameter `$disable_exit=false` to `retrieve_action()` and returns raw `$filetext` before headers. In `Controller.class.php` (outside diff), `Controller::act()` splats `$_GET` parameters positionally and echoes the return value as `text/html`. | **Missed** (0/3) | **Missed** (0/3) |
| `packet_06.diff` | `BENIGN-05` (`02a6a7793402`) | Benign Control (Security Fix) | `library/auth.inc.php`: **fixes** `CVE-2026-25476` by checking `isSessionExpired()` unconditionally before `skip_timeout_reset`. Should **not** be flagged as introducing a vulnerability. | **0 false security alerts** | **0 false security alerts** |
