# Security Review: `interface/forms/eye_mag/report.php` (new file) and related `custom_report.php`

**Recommendation: do not merge as-is.** The new file has a SQL injection, several stored XSS sinks, and missing access checks. The unchanged `custom_report.php` that includes it has additional injection and access-control flaws on the same request path, and this change makes some of them easier to reach.

Locations are given by function or code snippet because the diff has no stable line numbers in all cases.

---

## Findings in the new file (`report.php`)

### 1. SQL injection in `display_draw_image()`
- **Location:** `display_draw_image()`, `$sql = "SELECT * from documents where documents.url like '%".$filename."'";`, where `$filename = $base_name.".jpg"` and `$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW"`.
- **OWASP:** A03:2021 Injection.
- **Problem:** `$pid` and `$encounter` are concatenated into raw SQL. They originate from `$_REQUEST['ptid']` and `$_REQUEST['encid']`, and `$encounter` is also reassigned from DB row values through `extract()`. There is no parameter binding or type cast. Any authenticated user can inject through the URL, including UNION-based data extraction from any table. The function is called from every `display_draw_image("EXT"|"ANTSEG"|"NEURO"|"RETINA"|"IMPPLAN", ...)` call.
- **Severity:** High (Critical if the deployment exposes this endpoint broadly).
- **Fix:** Use `sqlQuery("SELECT * FROM documents WHERE url LIKE ?", array("%".$filename))`, and cast `$pid` and `$encounter` to int after validation.

### 2. Stored XSS: unescaped database free-text fields
- **Location:** `narrative()`:
  - `<?php echo $HPI1; ?>` (raw, not `text()`), and `$CHRONIC2`/`$CHRONIC3` echoed raw.
  - Impression/Plan loop: `echo $item['codetext']`, `echo $item['code']`, `echo $item['codetype']`, `echo $item['plan']` are all unescaped. `$item['plan']` only has newlines converted.
  - `echo $PLAN` (split on `|`) and `echo $PLAN2` are unescaped.
  - In the PDF branch, `$providerNAME` is echoed raw inside the `<img>`/`<hr>` block.
  - In `display_draw_image()`: `echo '<td>'.$note->get_note().'<br /><br /></td>';` is unescaped.
- **OWASP:** A03:2021 Injection (XSS).
- **Problem:** These fields are user-entered free text stored in the database. Any clinician or staff member can store script or HTML that executes in the viewer of the report. This includes the history-mouseover (`choice=TEXT`) view. Using `text()` on the same fields elsewhere in the file shows the inconsistency is accidental.
- **Severity:** High.
- **Fix:** Wrap every such field in `text()`, or in `nl2br(text(...))` where line breaks matter. Do not echo raw HTML from the database.

### 3. Missing authorization and patient binding (broken access control)
- **Location:** Top-level code of `report.php`:
  ```php
  if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
  if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
  if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
  ```
  The file never calls `acl_check()` for `patients`/`med`/`demo` or `encounters`.
- **OWASP:** A01:2021 Broken Access Control.
- **Problem:** Patient, encounter, and form identifiers come from the request and override any existing context. Because this file is included at global scope by `custom_report.php` (for every form directory the patient has), a request parameter can change `$pid` for the whole page. The file then renders clinical data for any patient ID the user supplies, without checking the user's patient-level permissions. Only a generic session check, if any, protects it.
- **Severity:** High.
- **Fix:** Take identifiers only from the controller context (for example, the `pid` set by `globals.php`/session). Enforce `acl_check('patients','med')` or equivalent in `narrative()`. Verify that the encounter and form belong to `$pid`, which the SQL partly does but only after the input is trusted.

### 4. Variable-variable injection from preferences table
- **Location:** Top-level code:
  ```php
  $query = "SELECT * FROM form_eye_mag_prefs where PEZONE='PREFS' AND id=? ...";
  while ($prefs = sqlFetchArray($result)) {
    $LOCATION = $prefs['LOCATION'];
    $$LOCATION = text($prefs['GOVALUE']);
  }
  ```
- **OWASP:** A03:2021 Injection (code/variable injection), A08:2021 Software and Data Integrity Failures.
- **Problem:** `LOCATION` is a column value used as a variable name. If any code path lets a user write arbitrary `LOCATION` values, that user can overwrite `$pid`, `$query`, `$form_id`, `$encounter`, `$GLOBALS`-related variables, and others in global scope. Because this runs at include time inside `custom_report.php`, it can corrupt the security-relevant state of the caller. Overwriting `$_SESSION` through a variable variable would also be a risk depending on the PHP version.
- **Severity:** Medium (High if the prefs write path is unvalidated; check the save code).
- **Fix:** Whitelist allowed `LOCATION` names. Store preferences in an array (`$prefs_arr[$LOCATION] = ...`) rather than in variable variables.

### 5. Unsafe `extract()` of database rows
- **Location:** `eye_mag_report()` and `narrative()`: `@extract($objQuery);` and `@extract($encounter_data);`.
- **OWASP:** A08:2021 Software and Data Integrity Failures; A05:2021 Security Misconfiguration (error suppression).
- **Problem:** The queries select `form_encounter.*` and `form_eye_mag.*`, which share columns such as `pid`, `id`, and `date`. `extract()` silently overwrites local variables, including `$pid`, `$encounter`, `$form_id`, and `$cols`, which then feed later queries. The `@` operator hides the warnings that would reveal this. The effect is confused state that can change which patient or encounter is queried.
- **Severity:** Medium.
- **Fix:** Select only needed columns with explicit names and aliases. Remove `@` and `extract()`.

### 6. Server-side request / local file inclusion via raw HTML in PDF generation
- **Location:** `custom_report.php` passes the full HTML to `HTML2PDF::writeHTML()`. The report emits unescaped HTML from items 2 above, and `$from_file` paths are placed in `<img src>` for PDF output.
- **OWASP:** A10:2021 Server-Side Request Forgery; A03:2021.
- **Problem:** Stored HTML such as `<img src="http://169.254.169.254/...">` or `<link>` tags is fetched server-side by the HTML2PDF renderer, which can reach internal hosts and read local files through `file://` URLs. Combined with item 2, a clinician can cause the server to fetch arbitrary URLs during PDF generation.
- **Severity:** Medium (depends on renderer configuration).
- **Fix:** Escape all content (item 2). Configure HTML2PDF to disallow remote and `file://` resources, or restrict its allowed paths.

### 7. Reflected XSS through `$pid` in an attribute
- **Location:** Photo block in `narrative()`: `$filetoshow = $GLOBALS['webroot']."/controller.php?document&retrieve&patient_id=$pid&document_id=..."`, echoed inside `<img src='...'>`. `display_draw_image()` has the same pattern.
- **OWASP:** A03:2021 Injection (XSS).
- **Problem:** `$pid` comes raw from `$_REQUEST['ptid']` and is not URL- or attribute-encoded. The photo query uses `foreign_id=?`, and MySQL's numeric coercion lets a value like `1' onerror='...` match patient 1, so the injected quote reaches the HTML. A crafted link can therefore execute script in the user's session.
- **Severity:** Medium.
- **Fix:** `attr(urlencode($pid))`, or cast `$pid` to int before use.

### 8. Missing output encoding in several other spots
- **Location:** `echo "<i>".xlt('Timing')...` branches are fine, but:
  - `<?php echo $CHRONIC2 ...` (see item 2).
  - `echo "<img src='$from_file'>"` in the PDF path with unvalidated `$from_file`.
  - `<?php echo xla(...) ?>` inside `title` attributes is fine, but `<span title="<?php xla('...'); ?>">` in the redness/desaturation row calls `xla()` without `echo`, so the title attribute is empty. This is a correctness bug, not a vulnerability.
- **OWASP:** A03:2021.
- **Severity:** Low.

### 9. Uninitialized and undefined variables used in security-relevant logic
- **Location:** `$bad` is used with `$bad++` and `if ($bad < '1')` without initialization. `$choice` is set only if `$_REQUEST['CHOICE']` (uppercase, a typo) is truthy. `left_overs()` and `full_report()` reference undefined `$table_name` and `$id`. `full_report()` has `return;` as its first statement, so the rest is dead code.
- **OWASP:** A05:2021 Security Misconfiguration (maintainability), A04:2021 Insecure Design.
- **Severity:** Low. Remove dead code, initialize variables, and fix the `CHOICE`/`choice` mismatch.

### 10. Unparameterized value from session in SQL
- **Location:** `narrative()`: `$sql = "select * from facility where id=" . $_SESSION['pc_facility'];`
- **OWASP:** A03:2021 Injection.
- **Problem:** Low exploitability because the session value is server-set, but this is an unquoted concatenation. It is easily copied elsewhere.
- **Severity:** Low. Bind as a parameter.

### 11. Audit logging gap
- **Location:** The report displays clinical data for patients and encounters without recording a view event.
- **OWASP:** A09:2021 Security Logging and Monitoring Failures.
- **Severity:** Low. Confirm whether the surrounding framework logs PHI access; if not, add an audit record.

---

## Findings in the unchanged `custom_report.php` (same request path, affected by this change)

### 12. SQL injection via `$pid` in immunizations and batch communication queries
- **Location:** `custom_report.php`, the `immunizations` branch: `where i1.patient_id = '$pid'`. The `batchcom` branch: `WHERE batchcom.patient_id='$pid'`.
- **OWASP:** A03:2021 Injection.
- **Problem:** `$pid` is unescaped and can be overridden by `report.php` from `$_REQUEST['ptid']` (item 3). Injection is possible through these queries, which are reached when a user requests the patient report.
- **Severity:** High.
- **Fix:** Parameterize, and cast `$pid` to int.

### 13. Command injection in ImageMagick conversion
- **Location:** `custom_report.php`, documents section: `exec("convert -density 200 \"$from_file\" -append -resize 850 \"$to_file\"");`
- **OWASP:** A03:2021 Injection (OS command injection).
- **Problem:** Filenames are interpolated into a shell command without `escapeshellarg()`. A document name containing `"`, `$(...)`, or backticks can execute commands. Exploitability depends on whether stored filenames are attacker-controlled (uploads, couch document IDs).
- **Severity:** High if uploads preserve original names; Medium otherwise.
- **Fix:** Use `escapeshellarg()` on both paths, or call ImageMagick through `proc_open` with an argument array.

### 14. Stored XSS across the custom report
- **Location:** `custom_report.php`:
  - Billing: `echo $b['code_type']...$b['code']...$b['code_text']` unescaped.
  - Issues: `echo $irow['title']`, `echo $irow['comments']`, `echo $dcode`, and `lookup_code_descriptions($dcode)` output are unescaped.
  - Documents: `echo "<h1>" ... $fname ...`, and `$note->get_note()` unescaped.
  - Batch communication: `$row{'msg_txt'}` (wrong key, which also yields a PHP 8 error) and unescaped output.
  - Printable header: `$titleres['DOB_TS']` and facility fields are echoed raw in the page header.
- **OWASP:** A03:2021 Injection (XSS).
- **Severity:** High.
- **Fix:** Wrap every output in `text()` or `attr()` as appropriate.

### 15. Missing authorization checks for patient sections
- **Location:** `custom_report.php`: `include_demographics`, `include_insurance`, `include_billing`, `include_notes`, `include_transactions`, `include_documents`. Only `history`, `immunizations`, and `procedures` check `acl_check('patients','med')`. The `$auth_demo` variable is computed but never used. Encounter forms are gated by an OR across several permissions, so any single permission exposes all encounter forms.
- **OWASP:** A01:2021 Broken Access Control.
- **Severity:** High.
- **Fix:** Enforce the matching ACL for each section, and require `demo` for demographics and insurance, `notes` for notes, and `coding`/`med` for billing and transactions.

### 16. Insecure direct object references: documents and issues
- **Location:** `custom_report.php`, `documents` loop: `new Document($document_id)` for any numeric ID in the POST array. The `issue_` branch queries `lists WHERE id = '$rowid'`.
- **OWASP:** A01:2021 Broken Access Control.
- **Problem:** No check that the document or issue belongs to the current `$pid`. A user can render another patient's documents, notes, and issues by supplying their IDs.
- **Severity:** High.
- **Fix:** Verify `documents.foreign_id == $pid` and `lists.pid == $pid` before rendering.

### 17. Dynamic function dispatch from request keys
- **Location:** `custom_report.php`: `call_user_func($res[1] . "_report", $pid, $form_encounter, $N, $form_id);`, where `$res[1]` is derived from a request key matching `^(.*)_(\d+)$`.
- **OWASP:** A03:2021 Injection / A04:2021 Insecure Design.
- **Problem:** User input chooses which function is called. The `_report` suffix limits this, but any function ending in `_report` that accepts these arguments can be invoked, and some may have side effects.
- **Severity:** Medium.
- **Fix:** Validate `$res[1]` against the set of form directories the patient actually has (already in `$formdir` from the `forms` table), and only then dispatch.

### 18. Unvalidated `$_GET`/`$_POST` passed into URLs
- **Location:** `custom_report.php`: `href="custom_report.php?printable=1&<?php print postToGet($ar); ?>"`. Keys and values are URL-encoded, so injection is limited, but the output is not attribute-escaped.
- **OWASP:** A03:2021.
- **Severity:** Low.

---

## Summary

| # | Location | Category | Severity |
|---|---|---|---|
| 1 | `display_draw_image` SQL | A03 Injection | High |
| 2 | `narrative` raw HPI/Plan/notes | A03 XSS | High |
| 3 | Top-level `$_REQUEST` binding, no ACL | A01 Broken Access Control | High |
| 4 | `$$LOCATION` prefs variables | A03/A08 | Medium |
| 5 | `@extract()` overwrites `$pid` etc. | A08/A05 | Medium |
| 6 | HTML2PDF fetches stored HTML | A10 SSRF | Medium |
| 7 | `$pid` in `<img src>` | A03 Reflected XSS | Medium |
| 8 | Misc. output encoding | A03 | Low |
| 9 | Uninitialized/dead code | A04/A05 | Low |
| 10 | `pc_facility` in SQL | A03 | Low |
| 11 | No PHI access audit | A09 | Low |
| 12 | `custom_report` `'$pid'` SQLi | A03 | High |
| 13 | `exec("convert ...")` | A03 OS command injection | High/Medium |
| 14 | `custom_report` XSS | A03 | High |
| 15 | Missing section ACLs | A01 | High |
| 16 | Document/issue IDOR | A01 | High |
| 17 | `call_user_func` on request key | A03/A04 | Medium |
| 18 | `postToGet` attribute context | A03 | Low |

**Priority fixes before merge:** items 1, 2, 3, 12, and 14 (SQL injection, stored XSS, and the patient-binding flaw that makes 12 reachable). Then address 13, 15, and 16. The remaining items can follow as hardening, though 4 and 5 should be fixed in this change because the new file introduces them.