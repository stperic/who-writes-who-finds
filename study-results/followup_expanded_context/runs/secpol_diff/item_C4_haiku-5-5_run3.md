# Security Review: `interface/forms/eye_mag/report.php` (new file, 2,060 lines)

**Verdict: Do not merge as-is.** The file has a reachable SQL injection, no per-patient authorization check, and many unescaped database values rendered into HTML and PDF output.

Several helpers it calls (`display_draw_section`, `report_header`, `getProviderName`, `Document`, `sqlQuery`, `get_couch_url`) are defined elsewhere and were not part of the diff. Findings that depend on them are marked as assumptions.

---

## Findings

### 1. SQL Injection (Critical)
- **Location:** `display_draw_image()`, the `$sql` construction:
  ```php
  $filename = $pid."_".$encounter."_".$side."_".$zone."_VIEW".".jpg";
  $sql = "SELECT * from documents where documents.url like '%".$filename."'";
  $doc = sqlQuery($sql);
  ```
- **OWASP:** A03:2021 Injection
- **Problem:** `$pid` and `$encounter` come from `$_REQUEST['ptid']` and `$_REQUEST['encid']` without validation. They are concatenated into raw SQL.
- **Reachability:** The `narrative()` query binds `$encounter` and `$pid` as parameters, but `@extract($encounter_data)` only overwrites them when that query returns a row. If `encid`/`ptid` match no row, the raw attacker-controlled values survive and reach `display_draw_image()`, which runs for the EXT, ANTSEG, NEURO, RETINA, and IMPPLAN sections. A `UNION`-based payload can then read arbitrary tables, including user password hashes.
- **Fix:** Use a parameterized query (`LIKE ?` with the wildcard built in PHP). Validate `ptid` and `encid` as positive integers before use.

### 2. Missing Authorization / Insecure Direct Object Reference (High)
- **Location:** Top of file (`$pid = $_REQUEST['ptid']`, `$encounter = $_REQUEST['encid']`, `$form_id = $_REQUEST['formid']`), `eye_mag_report()`, `narrative()`
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The page renders full PHI (demographics, exam findings, medications, signatures, photographs) for whatever `ptid`/`encid`/`formid` is supplied. There is no `acl_check('patients', 'demo'/'med')` call and no check that the encounter belongs to the patient or that the user may access that patient. The only session check is the global `globals.php` login.
- **Fix:** Call `acl_check()` for the patient's section before rendering. Verify that the encounter and form belong to `$pid` and are not deleted. Validate IDs as integers.

### 3. Stored Cross-Site Scripting via Unescaped Output (High)
Values from the database are echoed without `text()`/`attr()`/`xlt()`. Clinician-entered text can run script in the browsers of anyone who views the report, and in the PDF/fax renderer.

| Location | Unescaped value |
|---|---|
| HPI section | `echo $HPI1;`, `echo $HPI2;`, `echo $HPI3;` |
| Chronic problems | `echo "&nbsp;".$CHRONIC2`, `echo "&nbsp;".$CHRONIC3` |
| Orders | `echo $item."<br />";` (from `explode('|', $PLAN)`), `echo $PLAN2` |
| IMPPLAN | `echo $item['codetext']`, `echo $item['code']`, `echo $item['codetype']`, `echo $item['plan']` |
| PDF signature | `echo "...".$providerNAME."..."` (the `text()` call is only in the following span) |
| Draw images | `echo '<td>'.$note->get_note().'<br /><br /></td>';` |

- **Fix:** Wrap each value in `text()` or `htmlspecialchars()`. Use `text()` where the value is HTML-escaped and rendered as text. The IMPPLAN `plan` field already converts newlines to `<br />`, so escape first and then convert newlines.

### 4. Variable Variables and `extract()` from Database Data (Medium)
- **Location:**
  - `$$LOCATION = text($prefs['GOVALUE']);`, where `$LOCATION` is the `LOCATION` column of `form_eye_mag_prefs`
  - `@extract($objQuery);` in `eye_mag_report()`
  - `@extract($encounter_data);` in `narrative()`
  - `$$zone[$i]` and `${"ODSPH_$count_rx"}`-style dynamic variables
- **OWASP:** A08:2021 Software and Data Integrity Failures; A03:2021 (variable injection)
- **Problem:** Any column name or preference key can create or overwrite arbitrary variables in the global scope, including `$form_folder`, `$pid`, `$encounter`, `$PDF_OUTPUT`, `$web_root`, and `$display_Add`. The variables used in file paths and SQL then depend on whatever the database contains. `@` suppresses warnings, hiding failures.
- **Fix:** Replace `extract()` with explicit reads of required fields. Replace `$$LOCATION` with a whitelist, or store preferences in an array (`$prefs[$LOCATION]`).

### 5. Local Filesystem Paths in Image Sources, Especially for PDF Output (Medium)
- **Location:** `narrative()` (patient photo) and `display_draw_image()`:
  ```php
  $from_file = $GLOBALS["fileroot"] . "/sites/" . $_SESSION['site_id'] . '/documents/' . $from_pathname . '/' . $from_filename;
  echo "<img src='". $from_file."' style='width:220px;'>";
  ```
  Also: `$GLOBALS["webserver_root"] ."/interface/forms/.../sign_".$providerID.".jpg"`
- **OWASP:** A01:2021 (path handling), A10:2021 (SSRF-adjacent)
- **Problem:** When `$PDF_OUTPUT` is set, raw server filesystem paths are placed in `<img src>` for the HTML-to-PDF converter. A converter that resolves local paths or `file://` URLs can read arbitrary files into the generated PDF. The path is built partly from a document URL stored in the database. If `$PDF_OUTPUT` can be influenced by a request parameter (it is never set in this file, so its source is unknown), an attacker could trigger this branch.
- **Fix:** Do not embed filesystem paths in HTML. Read image bytes server-side and embed them as data URIs, or serve them through a controller that checks ACL. Sanitize `$from_pathname` and `$from_filename` and confirm the resolved path stays inside the site documents directory.

### 6. Unvalidated Request Inputs and Inconsistent Parameter Handling (Low)
- **Location:** Top of file:
  ```php
  if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
  ```
- **OWASP:** A03:2021, A04:2021 Insecure Design
- **Problem:** The guard tests `CHOICE` but reads `choice`, which is a logic bug. `$_REQUEST` accepts GET, POST, and cookies, so the source of input is ambiguous. `$choice` is later used to select which PHI sections render. `$cols` and `$choice` are compared loosely.
- **Fix:** Use `$_GET`/`$_POST` explicitly. Whitelist `choice` against `DRAW`, `TEXT`, `NARRATIVE`, and `cols` against `Fax`/`Report`, and use strict comparisons.

### 7. Error Suppression Hides Failures (Low)
- **Location:** `@extract(...)` in `eye_mag_report()` and `narrative()`
- **OWASP:** A09:2021 Security Logging and Monitoring Failures
- **Problem:** The `@` operator hides errors from both users and logs. Combined with the null-row behavior in Finding 1, failures are silent. `new DateTime($encounter_date)` throws on a null date, and that exception is not handled.
- **Fix:** Remove `@`. Check query results before use and log unexpected states.

### 8. Dead and Commented-Out Code With Injectable Patterns (Informational)
- **Location:**
  - `left_overs()` references undefined `$table_name` and `$id`, and calls `formFetch`.
  - `full_report()` returns immediately and contains unreachable code.
  - The commented DRAW block builds `"SELECT * from documents where url='file://".$file_location."'"` by concatenation.
- **Problem:** Re-enabling these blocks would reintroduce the Finding 1 pattern.
- **Fix:** Remove the dead code, or convert the SQL to parameterized form before re-enabling it.

### 9. Output Encoding Helper Misapplied (Low)
- **Location:** `report_ACT()`:
  ```php
  $term = nl2br(htmlspecialchars($term, ENT_NOQUOTES));
  ```
  Used for `NEURO_COMMENTS`.
- **Problem:** `ENT_NOQUOTES` leaves `'` and `"` unescaped. This is safe for text content but unsafe if the value is ever placed in an attribute. The function name also doesn't describe what it does.
- **Fix:** Use `text()` or `htmlspecialchars($term, ENT_QUOTES)`.

### 10. Non-Security Bugs Worth Fixing in the Same Pass
- `xla(...)` is called inside `title="<?php xla(...); ?>"` without `echo`, so the tooltip text is never output (several places in the Additional Findings and Anterior Segment sections).
- `<table style="report_vitals" ...>` puts a CSS class into the `style` attribute.
- `$GLOBALS['webroot']` is used in some places and `$GLOBALS['webserver_root']`/`$web_root` in others. Depending on the configuration, this can break image paths or cause unexpected file lookups.
- In `narrative()`, `$bad` is incremented without being initialized.

---

## Items Requiring Verification (Outside the Diff)
- **`display_draw_section()`, `report_header()`, `build_PMSFH()`, `show_PMSFH_report()`, `report_ACT()`'s callers, `report_header`:** These are in `eye_mag_functions.php` and `library/*`. The SQL and output-encoding practices there must be checked, since the report renders their output.
- **`Document::get_couch_url()`:** If it builds a URL from `$pid`/`$encounter` and fetches it server-side, it is an SSRF surface.
- **`$PDF_OUTPUT`, `$printable`, `$cols`:** These are read as globals but never set in this file. Confirm they cannot be set from request parameters.
- **`sqlQuery()` behavior:** Confirm whether stacked queries are allowed. The UNION-based exploit in Finding 1 works regardless.
- **CSRF:** This is a read-only view, so CSRF tokens are not expected here. Confirm that no state-changing action is triggered by these parameters.

---

## Summary

| # | Finding | OWASP | Severity |
|---|---|---|---|
| 1 | SQL injection in `display_draw_image()` via `ptid`/`encid` | A03 | Critical |
| 2 | No patient/encounter authorization check; IDOR via `ptid`/`encid`/`formid` | A01 | High |
| 3 | Stored XSS from unescaped HPI, plan, IMPPLAN, note, and provider output | A03 | High |
| 4 | Variable variables and `extract()` from DB/prefs | A08, A03 | Medium |
| 5 | Local filesystem paths embedded in HTML for PDF rendering | A01, A10 | Medium |
| 6 | `CHOICE`/`choice` mismatch; unvalidated `$_REQUEST` use | A03, A04 | Low |
| 7 | `@` error suppression | A09 | Low |
| 8 | Dead code containing the injectable pattern | Info | Info |
| 9 | `report_ACT()` uses `ENT_NOQUOTES` | A03 | Low |
| 10 | Non-security bugs (`xla` without `echo`, malformed `style` attribute, inconsistent globals) | — | Info |

**Recommended before merge:** fix Findings 1–3. Findings 4–5 should be fixed in this change or tracked with an issue, since the PDF path affects confidentiality.