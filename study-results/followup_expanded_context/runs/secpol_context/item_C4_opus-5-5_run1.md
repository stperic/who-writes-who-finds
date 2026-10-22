# Security Review: `interface/forms/eye_mag/report.php` (new file)

This file is pulled into `custom_report.php` with `include_once`, so its top-level code runs in that script's global scope. Several findings below depend on that.

**Overall verdict: do not merge as is.** The two critical issues are:
- request-supplied overrides of `$pid` and `$encounter` with no ACL check, and
- the unparameterized `LIKE` query in `display_draw_image()`.

Many PHI fields are also echoed without escaping.

---

## Findings in the new file

### 1. Request parameters override patient, encounter and form context with no authorization check
- **Location:** top of file, lines starting `if ($_REQUEST['ptid']) $pid = ...` (also `encid`, `formid`, `formname`)
- **Category:** A01 Broken Access Control (IDOR)
- **Severity:** **Critical**
- **Problem:**
  - `$pid`, `$encounter` and `$form_id` are replaced by request values.
  - `acl.inc` is included but `acl_check()` is never called.
  - Nothing verifies that the requested patient is the active patient or that the user may see them.
- **Impact via `custom_report.php`:**
  - The include runs before the report loop, so `?ptid=N` silently switches the global `$pid`.
  - Every later section of the custom report then shows patient N's data: demographics, history, insurance, billing, notes, transactions, immunizations and batchcom.
  - Any authenticated user can therefore read any patient's chart.
- **Second-order SQL injection:** `custom_report.php` builds raw SQL with this `$pid`, for example:
  - `"... where i1.patient_id = '$pid' ..."`
  - `"... WHERE batchcom.patient_id='$pid'"`
  
  These become injectable via `ptid`. This is only mitigated if the legacy GPC escaping in `globals.php` happens to cover `$_REQUEST` in that context.
- **Fix:**
  - Remove these overrides, or validate them as integers.
  - Verify that the encounter and form belong to the session `$pid`.
  - Enforce `acl_check('patients','med')` / `acl_check('encounters', ...)`.

### 2. SQL injection and cross-patient data leak in `display_draw_image()`
- **Location:** `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`
- **Category:** A03 Injection, and A01 Broken Access Control
- **Severity:** **High**
- **Problem:**
  - `$filename` is built from `$pid` and `$encounter`.
  - In `custom_report.php`, `$encounter` comes straight from the request value (`$form_encounter = $val`), and `$pid` can come from `ptid` (finding 1).
  - Both are concatenated into SQL without parameterization.
- **Data leak even without an attacker:**
  - The leading `%` makes this a suffix match, and `_` is a single-character wildcard.
  - So pid 1 / encounter 5 also matches `11_5_OU_EXT_VIEW.jpg`, which belongs to a different patient.
  - The resulting `document_id` is never checked against `foreign_id = $pid`, so another patient's drawing, and its notes, can be rendered.
- **Fix:** use a parameterized exact match, scoped to the patient:
  `WHERE url LIKE ? AND foreign_id = ?`, escaping `%` and `_`, or better, match on the full path.

### 3. Stored XSS: many PHI and clinical fields echoed without escaping
- **Category:** A03 Injection (XSS)
- **Severity:** **High** (these reports are viewed by clinicians and staff, so session hijacking is possible)
- **Unescaped fields:**
  - `echo $HPI1;` (`HPI2` and `HPI3` are escaped, `HPI1` is not)
  - `echo "&nbsp;".$CHRONIC2` and `$CHRONIC3`
  - `echo ($CTLOSVA?:"-")`
  - Motility cells `$MOTILITY_*`: DB values prefixed with `-` and echoed raw
  - Impression/Plan:
    - `$item['codetext']`, `$item['code']`, `$item['codetype']` are echoed raw.
    - `$item['plan']` is not escaped before `str_replace` turns newlines into `<br />`.
  - `$PLAN` items and `$PLAN2` echoed raw
  - `$note->get_note()` in `display_draw_image()`
  - `$providerNAME` in the PDF signature block
  - `$form_folder` and `$from_file` in `<img src>` (low risk, but should be escaped with `attr()`)
- **Fix:**
  - Wrap these in `text()` or `attr()`.
  - For the plan, use `nl2br(text($plan))`.

### 4. Variable variables populated from database preferences
- **Location:** `$$LOCATION = text($prefs['GOVALUE']);`
- **Category:** A04 Insecure Design (mass assignment of globals)
- **Severity:** **Medium**
- **Problem:**
  - Each row of `form_eye_mag_prefs` creates a global variable whose name comes from the `LOCATION` column.
  - Because this runs inside `custom_report.php`'s scope, a crafted pref row can overwrite security-relevant globals, such as:
    - `$pid`
    - `$auth_med` and `$auth_notes`
    - `$printable` and `$PDF_OUTPUT`
    - `$css_header`
  - Whether a user can write an arbitrary `LOCATION` depends on the eye_mag save endpoint.
- **Fix:** read prefs into an associative array and whitelist the allowed keys.

### 5. `@extract()` of query rows into local scope
- **Location:** `eye_mag_report()` and `narrative()`
- **Category:** A04 Insecure Design
- **Severity:** **Low to Medium**
- **Problem:**
  - Columns from `form_encounter.*` and `form_eye_mag.*` silently overwrite function variables such as `pid`, `encounter`, `id` and `form_id`.
  - The `@` hides errors.
  - The `narrative()` query does not join `forms.pid`, so the result for the encounter can be ambiguous.
- **Fix:** access row fields explicitly, e.g. `$row['...']`.

### 6. Raw SQL concatenation of a session value
- **Location:** `"select * from facility where id=" . $_SESSION['pc_facility']`
- **Category:** A03 Injection
- **Severity:** **Low**
- **Problem:** the value is session-controlled, but it should still be bound as a parameter.

### 7. Local filesystem paths passed to html2pdf
- **Location:** patient photo and drawings (`<img src='$from_file'>`), and the signature `sign_$providerID.jpg`
- **Category:** A01 / A05 Security Misconfiguration
- **Severity:** **Low**
- **Problem:**
  - Paths are derived from document URLs stored in the DB, with no canonicalization or check that they stay inside the documents directory.
  - A tampered document URL could make html2pdf embed arbitrary local image files.
  - The photo query also returns `documents.foreign_id = pid` across all categories joined loosely. Verify that the result is correct.

### 8. Functional bug that affects which content is shown
- **Location:** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`
- **Category:** none; this is a functional bug, not a vulnerability
- **Problem:** the condition checks `CHOICE` but reads `choice`, so the intended "summary only" mode is unreliable.

### 9. No access logging of PHI views
- **Category:** A09 Security Logging and Monitoring Failures
- **Severity:** **Low**
- **Problem:** the report is reachable directly with arbitrary patient IDs, but no explicit audit event (e.g. `newEvent`) records whose chart was viewed.

---

## Pre-existing issues in `custom_report.php` (relied on by this change)

| Location | Category | Severity | Issue |
|---|---|---|---|
| `"... where pid = '$pid'"`, the immunizations and batchcom queries | A03 | High | `$pid` is interpolated into raw SQL. This becomes exploitable together with finding 1. |
| `documents` loop: `new Document($document_id)` | A01 | High | Any numeric document ID from the request is rendered. There is no check that it belongs to `$pid`, and no ACL check for documents. |
| `exec("convert -density 200 \"$from_file\" ... \"$to_file\"")` | A03 (command injection) | Medium/High | The file path comes from the document URL and filename and is not passed through `escapeshellarg()`. |
| `call_user_func($res[1] . "_report", ...)` | A03 / A04 | Medium | The function name is derived from a request key. It is limited to functions ending in `_report`, but it is not whitelisted against the `formdir`s actually registered for the patient. |
| `getFormNameByFormdirAndFormid`, plus form and encounter IDs from the request | A01 | Medium | There is no check that the requested form or encounter belongs to `$pid`. |
| Raw echoes of facility fields, `$titleres` names, issue `title`/`comments`, billing `code_text`, `immunization_note`, batchcom data, `xl()` output | A03 (XSS) | Medium | These values are output without `text()` or `attr()`. |
| The `$_SESSION['pc_facility']` concatenation | A03 | Low | Same pattern as finding 6. |
| Search-bar query using `add_escape_custom` + `implode` | A03 | Low | Escaping is applied, but the query should be parameterized. |

---

## Recommendations
1. Remove the `$_REQUEST` overrides of `$pid`, `$encounter` and `$form_id`. Add explicit ACL checks and ownership checks (encounter and form belong to `$pid`).
2. Parameterize every query. Replace the `LIKE '%...'` document lookup with an exact match scoped to the patient.
3. Escape all output with `text()` or `attr()`, including the IMPPLAN, PLAN, HPI1, CHRONIC, motility and notes fields.
4. Replace `$$LOCATION` and `extract()` with explicit associative arrays.
5. Fix the pre-existing `custom_report.php` issues, especially the raw-SQL `$pid` usage, the unchecked document IDs, and the unescaped shell arguments in `exec()`.