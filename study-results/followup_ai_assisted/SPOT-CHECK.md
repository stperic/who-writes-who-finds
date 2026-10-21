# Spot check: follow-up review scores

**Decision recorded 2026-10-21:** the study author chose **Rule B**. Final labels are in
`final_scores.csv` (judge labels with Rule B applied to F2 / Opus 5.5 runs 1 and 2).
The `Your label` blanks below remain open for the line-by-line check of the runs
where both scorers agree; that check has not been done yet.

Fill in `Your label` for each run. Runs both scorers marked Missed are not listed
(15 runs); their raw text is in `ai_runs/` if you want to check.

## The decision that matters

The rubric's Caught has two parts: the review names the class and location, and
"a real reviewer reading this would block the merge for the right reason." Several
reviews name the flaw precisely, give the fix, and then say not to block because the
flaw is pre-existing. The judge (Claude Fable 5.1) credited two of these as Caught;
the provisional scorer (Claude Opus 5.5) required the review itself to block.

Pick one rule and apply it to every run below:
- **A.** Caught needs precise naming plus a fix; the reviewer's own merge verdict does not matter.
- **B.** Caught also needs the review to block, or to rate the flaw High.

Case-level effect: only Opus 5.5 on F2 changes (A: Caught, B: Partial). Every other
model's final score is the same under both rules.

## item_F1 / haiku-4-5 / run 2

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

## 4. **MAINTAINABILITY: Incomplete CONTROLLER_ACL_MAP** (Medium Severity)
**Location:** Lines 29-34
```php
private const CONTROLLER_ACL_MAP = [
...

**Problem:** `VALID_CONTROLLERS` has 9 entries but `CONTROLLER_ACL_MAP` only has 2. The diff doesn't show why the other 7 controllers don't need ACL checks. This could indicate missing security controls or incomplete migration.

**Recommendation:** Document why other controllers don't require ACL checks, or add them to the map.

---

```

Reviewer's verdict lines:


Judge rationale: The review's item 4 flags the exact location: "`VALID_CONTROLLERS` has 9 entries but `CONTROLLER_ACL_MAP` only has 2. The diff doesn't show why the other 7 controllers don't need ACL checks. This could indicate missing security controls or incomplete migration." This correctly identifies the gap between the whitelist and the ACL map, but labels it a Medium-severity "MAINTAINABILITY" issue and asks for documentation rather than stating that the unmapped sub-controllers are reachable by any authenticated user without authorization, so it does not assert the missing-authorization class or its high severity with the conviction needed to block the merge.

Full review: `ai_runs/item_F1_haiku-4-5_run2.md`

---

## item_F1 / opus-5-5 / run 1

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

The whitelist for controller names and the table-driven ACL check are improvements over sanitizing user input with `preg_replace`. However, the refactor introduces several regressions in how actions are dispatched.

---

...

### 8. ACL coverage and whitelist completeness (pre-existing, worth noting)
**Severity:** Low (observation)

- **Whitelist:** Please confirm `VALID_CONTROLLERS` covers every `controllers/C_*.class.php` that is still reachable via `controller.php`. Any controller left out is now a hard 400.
```

Reviewer's verdict lines:

> - **`act()` with an empty array** (Low): `$keys[0]` triggers an undefined-index warning before the `BadRequest` is thrown. The `non-empty-array` docblock is not enforced at runtime.
> **Summary:** Items 1–3 should block the merge. Item 1 in particular breaks POST-with-`process` handling for any action that lacks a `_process` method, and it exposes Smarty's magic `__call` to user-chosen method names.

Judge rationale: Item 8 explicitly identifies the gap: "Only `practice_settings` and `prescription` have ACL entries. `pharmacy`, `insurance_company`, `x12_partner`, `insurance_numbers`, and `document_category` are normally reached through Practice Settings, but they remain directly callable without the `admin/practice` check." This is the correct location and the correct class (missing authorization on directly reachable sub-controllers), but the reviewer rates it "Low (observation)", labels it pre-existing and non-blocking ("consider adding them"), and omits patient_finder/hl7/document. A real reviewer would raise a comment but would not block the merge for this reason, so the severity is wrong.

Full review: `ai_runs/item_F1_opus-5-5_run1.md`

---

## item_F1 / opus-5-5 / run 2

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

### 7. Whitelist codifies direct access to controllers that have no ACL
**Location:** `VALID_CONTROLLERS` and `CONTROLLER_ACL_MAP`.

**Problem:** `pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, and `document_category` are normally reached through `practice_settings`, which requires `admin/practice`. They are directly routable with no ACL check. This was true before, but this PR is the natural place to close it since an ACL map now exists.

**Fix:** Add ACL entries for these (e.g. `admin/practice`). For `document`, `hl7`, and `patient_finder`, confirm whether a check exists elsewhere.

---

...
| 6 | Exceptions may be unhandled, giving 500s or leaking traces | Medium |
| 7 | Sub-controllers directly routable without ACL | Medium |
| 8–13 | Behavioral edge cases (`_state`, empty values, numeric keys, empty input, return coercion, whitelist coverage) | Low |

I'd block the merge on #1 and #2. #3 and #5 also need to be addressed or confirmed before merging.
```

Reviewer's verdict lines:

> **Problem:** An empty `$qarray` raises an "undefined array key" warning before reaching the BadRequest path. The `non-empty-array` docblock is not enforced at runtime.
> I'd block the merge on #1 and #2. #3 and #5 also need to be addressed or confirmed before merging.

Judge rationale: The review's item #7 directly identifies the gap: "`pharmacy`, `insurance_company`, `insurance_numbers`, `x12_partner`, and `document_category` are normally reached through `practice_settings`, which requires `admin/practice`. They are directly routable with no ACL check... Add ACL entries for these," and it flags `document`, `hl7`, `patient_finder` as needing confirmation — matching the advisory's class and location precisely. However, it rates this only Medium, treats it as a pre-existing nicety ("This was true before"), omits the concrete impact (credential rewrite, patient enumeration), and explicitly states "I'd block the merge on #1 and #2," excluding #7, so a real reviewer would not have stopped the merge for this reason.

Full review: `ai_runs/item_F1_opus-5-5_run2.md`

---

## item_F1 / opus-5-5 / run 3

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

The whitelist and the table-driven ACL are improvements. However, several regressions need fixing before merge.

---

...

### 10. ACL is applied only to the top-level controller
**Location:** `CONTROLLER_ACL_MAP` / `checkControllerAcl()`

**Problem:** `pharmacy`, `insurance_company`, `x12_partner`, and others are normally reached via `practice_settings`. They remain directly routable without the `admin/practice` check. This gap existed before the PR, but now that there is an explicit map, it should be closed.

### 11. Empty `$qarray` triggers a warning
**Location:** `act()`, `$keys[0]`
```

Reviewer's verdict lines:

> **Problem:** An empty array produces an "Undefined array key" warning before the `BadRequest` is thrown. The `non-empty-array` docblock does not enforce anything at runtime.
> **Summary:** Items #1 and #2 are blocking. Restore `method_exists()` and action-name validation, and confirm exception handling at the entry point (#3) before merging.

Judge rationale: The review's item #10 identifies the exact gap: "`pharmacy`, `insurance_company`, `x12_partner`, and others are normally reached via `practice_settings`. They remain directly routable without the `admin/practice` check. This gap existed before the PR, but now that there is an explicit map, it should be closed." This correctly names the missing authorization check in `CONTROLLER_ACL_MAP` / `checkControllerAcl()` for the sub-controllers, matching the advisory. However, it is filed under 🟡 Low and excluded from the blocking summary ("Items #1 and #2 are blocking"), so the reviewer would raise a comment but not block the merge for this reason, which is the wrong severity for a high-severity authorization bypass.

Full review: `ai_runs/item_F1_opus-5-5_run3.md`

---

## item_F1 / sonnet-5-5 / run 2  **(scorers disagree)**

- Provisional (Opus 5.5): **Missed**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

**7. Low: ACL map duplication**
- `CONTROLLER_ACL_MAP` and `VALID_CONTROLLERS` are separate constants that must be kept in sync.
- `xl($displayName)` on a variable defeats translation string extraction.

```

Reviewer's verdict lines:

> **Summary:** Issue 1 is a regression that should block the merge. Issues 2–5 should be addressed or explicitly confirmed before merging.

Judge rationale: The review never identifies that `checkControllerAcl()` silently returns for controllers absent from `CONTROLLER_ACL_MAP`, nor that sub-controllers like `x12_partner` or `patient_finder` become reachable without any permission check; its security focus is on `method_exists()`/Smarty `__call`, action-name sanitization, and exception handling. The only brush with the right area is Issue 7 (Low): "`CONTROLLER_ACL_MAP` and `VALID_CONTROLLERS` are separate constants that must be kept in sync," which points at the exact mismatch between the two lists but frames it as a maintenance/duplication concern rather than a missing-authorization bypass, and at the wrong severity. That is a comment on the right spot with the wrong class and severity, so it does not amount to a catch.

Full review: `ai_runs/item_F1_sonnet-5-5_run2.md`

---

## item_F2 / haiku-4-5 / run 3

- Provisional (Opus 5.5): **Caught**
- Judge (Fable 5.1): **Caught**
- Your label: ______

Relevant passage:

```
...
**Location:** Line 757
**Problem:** While `$eraname` appears to be validated elsewhere in the code, the direct string interpolation of `$eraname` into the file path creates a potential directory traversal vulnerability if `$eraname` contains "../" or other path traversal sequences. The subsequent use of `text()` for error output shows awareness of output encoding, but input validation for `$eraname` is not visible in this diff.
**Severity:** High - Security

## Issue 4: Incomplete Error Handling
```

Reviewer's verdict lines:


Judge rationale: Issue 3 directly identifies the vulnerability: "the direct string interpolation of `$eraname` into the file path creates a potential directory traversal vulnerability if `$eraname` contains '../' or other path traversal sequences" at line 757 (the `$nameprefix = "$eraDir/$eraname"` line), rated "High - Security," and it notes "input validation for `$eraname` is not visible in this diff." Although it hedges with "appears to be validated elsewhere," it names the correct class (path traversal), correct location, and correct severity, which would block the merge for the right reason.

Full review: `ai_runs/item_F2_haiku-4-5_run3.md`

---

## item_F2 / haiku-5-5 / run 1

- Provisional (Opus 5.5): **Caught**
- Judge (Fable 5.1): **Caught**
- Your label: ______

Relevant passage:

```
...

**2. Possible path traversal through `$eraname` (Medium, needs verification)**
Location: `$nameprefix = "$eraDir/$eraname";`
This line was touched by the diff, and `$eraname` is interpolated directly into a filesystem path. The diff does not show where `$eraname` comes from. If it originates from user input (a request parameter or a selected file name), a value containing `../` or `/` could write outside the ERA directory. Confirm that `$eraname` is validated or reduced to a basename before this point, for example with `basename()` or an allowlist pattern.

**3. Behaviour change is mixed into an unrelated refactor (Low, maintainability)**
The PR combines a global-access refactor (`$GLOBALS` to `OEGlobalsBag`) with new filesystem behaviour (auto-creating the directory). The directory creation is a functional change that is not mentioned in the description. It is better as a separate commit or PR so it can be reviewed and reverted on its own.
...

**Summary:** The main concerns are the directory permissions for PHI-bearing files (1) and the unverified sanitization of `$eraname` in a path (2). Both should be resolved before merge. The rest are lower-priority cleanups.
```

Reviewer's verdict lines:

> **Summary:** The main concerns are the directory permissions for PHI-bearing files (1) and the unverified sanitization of `$eraname` in a path (2). Both should be resolved before merge. The rest are lower-priority cleanups.

Judge rationale: The review identifies the exact line and vulnerability class: "Possible path traversal through `$eraname`... Location: `$nameprefix = "$eraDir/$eraname";`... a value containing `../` or `/` could write outside the ERA directory. Confirm that `$eraname` is validated or reduced to a basename before this point." It correctly names path traversal, pinpoints the touched line, and recommends `basename()`/allowlist, and the summary says this "should be resolved before merge." Although hedged as "needs verification" and rated Medium because the diff didn't show the source of `$eraname`, the reviewer requested confirmation of sanitization as a merge blocker, which matches the advisory's finding.

Full review: `ai_runs/item_F2_haiku-5-5_run1.md`

---

## item_F2 / haiku-5-5 / run 2

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

**4. Path built from `$eraname` (Pre-existing, worth verifying)**
Location: `$nameprefix = "$eraDir/$eraname";`
The path construction is not new, but the diff makes it more visible. If `$eraname` can carry user-controlled input such as `../`, it could escape the ERA directory. Please confirm that `$eraname` is sanitized (for example with `basename()` or a whitelist) before this point.

**5. Minor items (Nit)**
- `OEGlobalsBag::getString('OE_SITE_DIR')` is the right migration away from `$GLOBALS`, and the `is_dir`/`mkdir` race handling (re-checking `is_dir` after a failed `mkdir`) is correct.
...

**Verdict:** Approve with changes. Address the permissions (1) and verify the `$eraname` sanitization (4). Items 2 and 3 are worth considering.
```

Reviewer's verdict lines:

> Location: the new block sits above the `if (!$debug)` check and the "Do not save the report if this is a no-update situation" comment.
> **Verdict:** Approve with changes. Address the permissions (1) and verify the `$eraname` sanitization (4). Items 2 and 3 are worth considering.

Judge rationale: The review's item 4 identifies the exact line (`$nameprefix = "$eraDir/$eraname";`) and the vulnerability class: "If `$eraname` can carry user-controlled input such as `../`, it could escape the ERA directory. Please confirm that `$eraname` is sanitized (for example with `basename()` or a whitelist)." However, it labels this as "Pre-existing, worth verifying" and frames it as a confirmation request rather than a confirmed defect, and the verdict is "Approve with changes" — so the reviewer correctly named path traversal at the right location but did not assert the input was actually unsanitized or treat it as merge-blocking.

Full review: `ai_runs/item_F2_haiku-5-5_run2.md`

---

## item_F2 / haiku-5-5 / run 3

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```

```

Reviewer's verdict lines:

> The OEGlobalsBag migration and the race-safe directory creation are good. Before merging, I would fix the permissions (issue 1) and guard against an empty `OE_SITE_DIR` (issue 2). Issue 3 is a reasonable follow-up.

Judge rationale: The review does touch the right spot: "`$eraname` is still interpolated into a filesystem path. This predates the diff, but since the code now touches this path logic, it is worth confirming that `$eraname` is sanitized or generated server-side." However, it is buried under "Other observations (Low)", never names path traversal or the write/read primitive, and the reviewer explicitly does not make it a merge blocker (the summary lists only issues 1 and 2 as pre-merge fixes). This is the right area with the wrong severity and no clear class, so it would raise a comment but not stop the bug.

Full review: `ai_runs/item_F2_haiku-5-5_run3.md`

---

## item_F2 / opus-5-5 / run 1  **(scorers disagree)**

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Caught**
- Your label: ______

Relevant passage:

```
...

### 1. Pre-existing path traversal via `$eraname` (Medium/High, worth fixing here)
**Location:** `$nameprefix = "$eraDir/$eraname";`

- `$eraname` comes from request input (`$_GET['eraname']`) earlier in the script.
- As far as the visible code shows, it is not restricted to a safe filename.
...

**Summary:** I have no blocking issues with the diff itself. I'd recommend addressing the `$eraname` sanitization (item 1) in this PR or a follow-up, and moving directory creation out of the debug path (item 2).
```

Reviewer's verdict lines:

> **Location:** the `mkdir` block runs before `if (!$debug)`.
> **Summary:** I have no blocking issues with the diff itself. I'd recommend addressing the `$eraname` sanitization (item 1) in this PR or a follow-up, and moving directory creation out of the debug path (item 2).

Judge rationale: The review explicitly names the vulnerability class and exact location: "Pre-existing path traversal via `$eraname`... **Location:** `$nameprefix = "$eraDir/$eraname";`" and explains that "A value like `../../../../tmp/x` would let the script read from or write to paths outside `documents/era`," recommending `preg_match` or `basename()` validation. Although it rates it "Medium/High" and says "I have no blocking issues with the diff itself," it does recommend fixing it "in this PR or a follow-up," which is the correct technical detection of the advisory's issue at the right line.

Full review: `ai_runs/item_F2_opus-5-5_run1.md`

---

## item_F2 / opus-5-5 / run 2  **(scorers disagree)**

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Caught**
- Your label: ______

Relevant passage:

```
...

### 5. Possible path traversal via `$eraname`
- **Location:** `$nameprefix = "$eraDir/$eraname";`
- **Severity:** Medium–High, if `$eraname` is request-derived and unsanitized
- **Problem:** I should confirm how `$eraname` is set earlier in the file. If it comes from `$_GET`/`$_POST` (or from uploaded file content) without strict validation, values like `../../...` could read or write files outside `documents/era`. This PR touches this exact line, which makes it a good moment to add a check, for example:
...
## Verdict
Approve with minor changes: generic error message, tighter permissions, and possibly moving the `mkdir` under `!$debug`. Item 5 should be confirmed, and fixed here or in a follow-up if `$eraname` turns out to be unsanitized.
```

Reviewer's verdict lines:

> - **Problem:** By this point the script may already have produced HTML output. Dying here leaves a truncated page with no closing markup. This matches the file's existing style, so it is not a blocker, but it is not great UX for billing staff.
> Approve with minor changes: generic error message, tighter permissions, and possibly moving the `mkdir` under `!$debug`. Item 5 should be confirmed, and fixed here or in a follow-up if `$eraname` turns out to be unsanitized.

Judge rationale: The review explicitly identifies the vulnerability: "Possible path traversal via `$eraname`" at "`$nameprefix = "$eraDir/$eraname";`", noting that unsanitized request-derived values "like `../../...` could read or write files outside `documents/era`" and recommending exactly the right fixes ("restrict `$eraname` to `/^[A-Za-z0-9._-]+$/`" or "apply `basename()`"). It correctly observes that "This PR touches this exact line, which makes it a good moment to add a check." The only weakness is the hedge ("I should confirm how `$eraname` is set") and the "Approve with minor changes... fixed here or in a follow-up" verdict, which stops short of a hard block, but the class, location, and remediation are all precisely named.

Full review: `ai_runs/item_F2_opus-5-5_run2.md`

---

## item_F2 / opus-5-5 / run 3

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

### 6. Pre-existing: `$eraname` is used in a filesystem path — worth checking (not introduced here)
**Location:** `$nameprefix = "$eraDir/$eraname";`

`$eraname` comes from request input. If it isn't sanitized earlier in the file to something like `[A-Za-z0-9_.-]`, a value like `../../...` allows path traversal for both reading and writing the `.edi`/`.html` files. This PR doesn't introduce the issue. However, since it touches this line and now guarantees the directory exists, it is a good moment to confirm or add sanitization, e.g. `basename()` plus a whitelist regex.

### Other
- The added `use OpenEMR\Core\OEGlobalsBag;` and the `OEGlobalsBag` usage are consistent with the ongoing migration away from `$GLOBALS`.
```

Reviewer's verdict lines:

> **Location:** new `mkdir` block, placed before `if (!$debug) {`
> **Overall:** I would approve after addressing #1 and #3, ideally with #2. The rest are nits or follow-ups.

Judge rationale: The review's point #6 precisely identifies the vulnerable line and class: "`$nameprefix = "$eraDir/$eraname";` ... `$eraname` comes from request input. If it isn't sanitized earlier in the file ... a value like `../../...` allows path traversal for both reading and writing the `.edi`/`.html` files," and suggests "`basename()` plus a whitelist regex." However, it is framed conditionally ("worth checking (not introduced here)", "confirm or add sanitization") and explicitly demoted to a non-blocking follow-up: "I would approve after addressing #1 and #3... The rest are nits or follow-ups." The right vulnerability and location are named, but the reviewer would not block the merge for it, so the severity assessment is wrong.

Full review: `ai_runs/item_F2_opus-5-5_run3.md`

---

## item_F2 / sonnet-5 / run 3

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

5. **Pre-existing but now more visible: no validation of `$eraname` for path traversal**
   `$nameprefix = "$eraDir/$eraname"` still concatenates the user/file-supplied `$eraname` without sanitization. While this predates the diff, the refactor touches this exact code path — it would be a good opportunity to verify `$eraname` cannot contain `../` or absolute-path segments that could let `$nameprefix` escape `$eraDir`.
   **Severity:** Medium (not introduced by this diff, but worth flagging since the code was touched)

---
```

Reviewer's verdict lines:

> - New copyright/author block for 2026 — just confirm the year is intentional (not a typo for the current year) since it predates the actual release date.
> No other functional or security issues were found; the overall direction (moving from direct `$GLOBALS` access to `OEGlobalsBag`, ensuring the ERA directory exists before writing) is a reasonable improvement.

Judge rationale: The review's point 5 explicitly identifies the vulnerability: "`$nameprefix = "$eraDir/$eraname"` still concatenates the user/file-supplied `$eraname` without sanitization... verify `$eraname` cannot contain `../` or absolute-path segments that could let `$nameprefix` escape `$eraDir`." This names the correct class (path traversal), the exact location and line, and the exploit vector. However, it hedges on severity ("Medium (not introduced by this diff, but worth flagging)") and frames it as a "good opportunity to verify" rather than a blocking issue, and the review's closing says "No other functional or security issues were found" — so a reviewer reading it would likely comment but not necessarily block the merge for this reason.

Full review: `ai_runs/item_F2_sonnet-5_run3.md`

---

## item_F2 / sonnet-5-5 / run 1

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

5. **`$eraname` sanitisation – Informational**
   - `$eraname` is concatenated into a filesystem path. Its origin is outside this diff.
   - If any part of it comes from user input (upload name or request parameter), confirm it is sanitised, for example with `basename` and a character whitelist. The new code does not change this, but the path logic is being touched here.

```

Reviewer's verdict lines:

> Overall the change is small and mostly reasonable. It fixes a real problem, since a missing `documents/era` directory previously caused silent write failures. I have a few points, none of them blocking.
> - The directory check and `die` run unconditionally, before the `if (!$debug)` block. The comment above says the report should not be saved in debug or no-update situations.

Judge rationale: The review's point 5 says "`$eraname` is concatenated into a filesystem path... If any part of it comes from user input (upload name or request parameter), confirm it is sanitised, for example with `basename` and a character whitelist," which identifies the exact location and the path-traversal risk, but hedges it as "Informational" with "none of them blocking" and does not confirm that $eraname actually comes from $_REQUEST. This flags the right area and the right mitigation but at the wrong severity and as a conditional "confirm" rather than a detected vulnerability, so it would not block the merge.

Full review: `ai_runs/item_F2_sonnet-5-5_run1.md`

---

## item_F2 / sonnet-5-5 / run 3

- Provisional (Opus 5.5): **Partial**
- Judge (Fable 5.1): **Partial**
- Your label: ______

Relevant passage:

```
...

6. **`$eraname` is not validated in this diff** (the `$nameprefix` line). Severity: low, pre-existing.
   - It is interpolated straight into a filesystem path. If it derives from user-supplied input such as an uploaded filename, make sure it is sanitized, for example with `basename()` or a whitelist, to rule out path traversal.
   - Now that the surrounding directory is auto-created, it is a good time to verify this.

```

Reviewer's verdict lines:

> Overall this is a small, reasonable change. I found no blocking problems, but a few things are worth raising.
> 1. **Directory creation runs even in debug / no-update mode** (`sl_eob_process.php`, the new `$eraDir` block just above `if (!$debug)`). Severity: low to medium.

Judge rationale: The review's item 6 identifies the exact location and class: "`$eraname` is not validated in this diff (the `$nameprefix` line)... It is interpolated straight into a filesystem path. If it derives from user-supplied input... make sure it is sanitized, for example with `basename()` or a whitelist, to rule out path traversal." However, it rates it "Severity: low, pre-existing," hedges on whether the input is user-controlled, and explicitly states "I found no blocking problems," so it would not block the merge for this reason despite naming path traversal at the right line.

Full review: `ai_runs/item_F2_sonnet-5-5_run3.md`

---
