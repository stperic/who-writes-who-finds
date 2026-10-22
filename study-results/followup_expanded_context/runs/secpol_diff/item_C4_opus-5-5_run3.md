# Security Review: `interface/forms/eye_mag/report.php`

## Summary

This new file renders protected health information (PHI). It has one critical SQL injection, a broken access control problem, and many stored and reflected XSS sinks. Several patterns (`extract()`, variable variables, string-built SQL) make the code fragile. **Do not merge as-is.**

| # | Issue | OWASP 2021 | Severity |
|---|-------|-----------|----------|
| 1 | SQL injection in `display_draw_image()` | A03 Injection | **Critical** |
| 2 | Request parameters override patient, encounter and form IDs with no ACL check | A01 Broken Access Control | **High** |
| 3 | Stored XSS from unescaped clinical fields | A03 Injection (XSS) | **High** |
| 4 | Reflected XSS from `ptid` / `encid` in `<img src>` | A03 Injection (XSS) | **High** |
| 5 | Cross-patient document disclosure through the `LIKE '%…'` lookup | A01 / A04 Insecure Design | **Medium** |
| 6 | SQL concatenation of `$_SESSION['pc_facility']` | A03 Injection | **Medium** |
| 7 | Variable variables and `extract()` overwrite the local scope | A04 / A08 Data Integrity | **Medium** |
| 8 | Server filesystem paths emitted into output | A05 Misconfiguration / Info Disclosure | **Low** |
| 9 | Missing PHI access audit and error suppression with `@` | A09 Logging/Monitoring | **Low** |

---

## 1. SQL Injection in `display_draw_image()` (Critical)

**Location:** `display_draw_image()`

```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```

**Problem:**
- `$pid` and `$encounter` come straight from `$_REQUEST['ptid']` and `$_REQUEST['encid']` at the top of the file.
- They pass unmodified into `narrative()` and then into `display_draw_image()`.
- A request such as `?ptid=1' UNION SELECT ... -- ` gives full SQL injection against the EMR database. That exposes every patient record, user password hashes, and possibly write access depending on the DB user.
- `$sanitize_all_escapes=true` disables the legacy magic-quote style escaping, so nothing mitigates this.

**Fix:**
- Use a bound parameter: `sqlQuery("SELECT * FROM documents WHERE url LIKE ? AND foreign_id = ?", array('%'.$filename, $pid))`.
- Cast or validate `$pid` and `$encounter` as integers at entry.

---

## 2. Broken Access Control: Caller-Controlled Patient, Encounter and Form IDs (High)

**Location:** top of file

```php
if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];
if ($_REQUEST['encid']) $encounter=$_REQUEST['encid'];
if ($_REQUEST['formid']) $form_id = $_REQUEST['formid'];
if ($_REQUEST['formname']) $form_name=$_REQUEST['formname'];
```

**Problem:**
- Any authenticated user can replace the session patient (`$pid`) with an arbitrary patient ID. They can then view another patient's full eye exam, history, photo, prescriptions and signature.
- `acl.inc` is included, but `acl_check()` is never called. There is no check for `patients/med` or the encounter/form ACL.
- There is no check that the user is allowed to see this patient, or that the encounter belongs to the patient's facility or provider.

This is a classic IDOR on PHI, which is also a HIPAA concern.

**Fix:**
- Do not override `$pid` from the request. Use the session patient. If cross-patient viewing is truly needed (e.g., from taskman/fax), enforce `acl_check('patients','med')` and verify ownership explicitly.
- Validate that `$encounter` and `$form_id` belong to `$pid` before rendering. Note that the `form_eye_mag_wearing` and `_impplan` queries trust `$form_id` from the request.

---

## 3. Stored XSS from Unescaped Clinical Data (High)

**Locations:** in `narrative()` and `display_draw_image()`. Each line below is echoed raw, without `text()`:

| Code | Notes |
|------|-------|
| `echo $HPI1;` | HPI free text |
| `echo "&nbsp;".$CHRONIC2."<br />";` and `$CHRONIC3` | `CHRONIC1` is escaped, these two are not |
| `echo ($CTLOSVA?:"-");` | Every sibling field uses `text()` |
| `echo $item['codetext']`, `echo $item['code']`, `$item['codetype']` | IMPPLAN rows |
| `echo $item['plan']` | Newlines are converted to `<br />`, but the content is never escaped |
| `echo $item."<br />"` in the `$PLAN` loop, and `echo $PLAN2` | |
| `echo '<td>'.$note->get_note().'...` | Document notes |
| `$providerNAME` in the PDF signature block | |
| `echo $MOTILITY_RRSO` and the rest of `$MOTILITY_*` | Built by string-concatenating a DB value with `-`; not escaped |
| `echo $RX_TYPE` | Safe (output of `xlt()`), listed only for completeness |

**Problem:**
- Any user who can write to these form fields can plant script. That includes staff with limited rights, or data imported from external systems or the patient portal.
- The script executes in the browser of every clinician or admin who views the report or encounter-history mouseover. That enables session hijacking and actions performed as the victim.
- The same HTML is also fed to html2pdf, where injected tags can trigger local-file or remote-resource fetches (see #8).

**Fix:**
- Wrap every DB-sourced value in `text()`, or `attr()` in attributes.
- For `plan` and comments, use `nl2br(text($value))` rather than raw `str_replace` to `<br />`. `report_ACT()` already does this correctly.

---

## 4. Reflected XSS via `ptid` / `encid` (High)

**Locations:**
- Patient photo: `$filetoshow = ...controller.php?document&retrieve&patient_id=$pid&document_id=...` followed by `echo "<img src='".$filetoshow."' ...>"`
- `display_draw_image()`: the same pattern with `$pid`, plus SQL injection-controlled `$doc['id']`.

**Problem:**
- `$pid` is attacker-supplied and is placed unescaped inside a single-quoted attribute.
- MySQL casts a string such as `1' onerror='alert(document.cookie)` to `1` when comparing with `documents.foreign_id`. So the photo lookup still succeeds and the payload is reflected.
- A crafted link sent to a logged-in clinician executes script.

**Fix:**
- Cast `$pid` with `(int)` at input.
- Build URLs with `attr()` / `urlencode()`.

---

## 5. Cross-Patient Document Disclosure via `LIKE` Pattern (Medium)

**Location:** `display_draw_image()`: `documents.url like '%{pid}_{encounter}_OU_{zone}_VIEW.jpg'`

**Problem:**
- The leading `%` means patient `1`, encounter `5` matches files named `11_5_…`, `21_5_…` and so on.
- `_` is itself a single-character LIKE wildcard.
- The query does not filter by `foreign_id`.

As a result, one patient's report can display another patient's drawings and document notes. This happens even without an attacker and is a data integrity and confidentiality issue.

**Fix:**
- Query by `foreign_id = ?` plus an exact URL or name match.
- Escape LIKE metacharacters if a LIKE match is truly needed.

---

## 6. SQL Concatenation of Session Value (Medium)

**Location:** `narrative()`

```php
$sql = "select * from facility where id=" . $_SESSION['pc_facility'];
```

**Problem:**
- `pc_facility` is populated from user-submitted calendar and facility selections elsewhere in OpenEMR, so it is not a trusted constant.
- Concatenation enables second-order SQL injection.

**Fix:** `sqlQuery("SELECT * FROM facility WHERE id = ?", array($_SESSION['pc_facility']))`.

---

## 7. Variable Variables and `extract()` Overwrite Scope (Medium)

**Locations:**
- Top level: `$$LOCATION = text($prefs['GOVALUE']);`
- `@extract($objQuery);` in `eye_mag_report()` and `@extract($encounter_data);` in `narrative()`
- `left_overs()`: `$$key=$value`. This is dead code but dangerous if revived.

**Problem:**
- `LOCATION` values from `form_eye_mag_prefs` can create or overwrite any global variable. The user controls these values through the preferences UI. Targets include `$pid`, `$encounter`, `$form_id`, `$choice`, `$PDF_OUTPUT` and `$GLOBALS`-adjacent names.
- `extract()` with the default `EXTR_OVERWRITE` lets any DB column overwrite local variables, including `pid`, `form_id`, `encounter` and `id`. Through the `global` references it can also overwrite `$PDF_OUTPUT`, `$form_folder` and `$printable`.
- `$form_folder` is later concatenated into file paths and HTML.
- This undermines the integrity of every later security decision. The `@` also hides warnings that would reveal the problem.

**Fix:**
- Replace with explicit array access (`$encounter_data['HPI1']`), or use `extract($row, EXTR_SKIP)` with a whitelist prefix.
- Store prefs in an array (`$prefs[$LOCATION]`), not variable variables.

---

## 8. Filesystem Path Disclosure and PDF Local-Resource Handling (Low)

**Locations:**
- `$from_file` (`$GLOBALS['fileroot']/sites/...`) is emitted in `<img src>` when `$PDF_OUTPUT` is set.
- The `eom.jpg` background uses `fileroot`.
- Signature image path.

**Problem:**
- Absolute server paths are exposed in generated HTML.
- Combined with the XSS in #3, injected `<img src="/etc/...">` or remote URLs reach html2pdf. Depending on the renderer, this can lead to local file reads or SSRF (A10).

**Fix:** Escape all data before PDF rendering, and restrict the PDF renderer to an allowed directory with remote fetches disabled.

---

## 9. Logging and Monitoring (Low)

**Problem:**
- The report exposes PHI for an arbitrary `ptid`, but no explicit audit event records which user viewed which patient's report. This depends on OpenEMR's generic query logging being enabled.
- `@extract` suppresses errors that would aid detection.

**Fix:** Log report access (`newEvent(...)`) with the user, patient and encounter, and remove `@` suppression.

---

## Related Code Relied Upon (Not in Diff, Should Be Reviewed)

- **`php/eye_mag_functions.php`:** `build_PMSFH`, `show_PMSFH_report`, `report_header`, `display_draw_section`. These receive the attacker-controlled `$pid` / `$encounter`. Verify that they use bound parameters and escape output.
- **`controller.php?document&retrieve`:** this report relies on it for document access control when displaying the photo and drawings. Confirm it enforces ACL per `patient_id` rather than trusting the parameter.
- **Functional bug:** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` checks the wrong case. It is not exploitable as written, but if fixed, `$choice` should be whitelisted (`DRAW`, `TEXT`, `narrative`).

## Recommended Minimum Before Merge

1. Parameterize all SQL (#1, #6), and cast IDs to `int` at entry.
2. Add `acl_check()` and patient/encounter/form ownership validation. Stop overriding `$pid` from the request (#2).
3. Escape every DB- or request-derived value on output with `text()` / `attr()` (#3, #4).
4. Remove `extract()` and variable-variable assignments (#7).
5. Fix the document lookup to use `foreign_id` and an exact match (#5).