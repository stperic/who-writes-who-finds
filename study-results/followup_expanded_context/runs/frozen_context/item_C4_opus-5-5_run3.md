# Review: `interface/forms/eye_mag/report.php`

`custom_report.php` loads this file with `include_once` at **global scope** (once per distinct `formdir`). That makes the top-level code especially risky, because it runs in the same scope as the variables the patient report depends on.

---

## Security

### 1. Request parameters overwrite the global patient and encounter — High
- **Location:** top of file, `if ($_REQUEST['ptid']) $pid = $_REQUEST['ptid'];` and the lines for `encid`, `formid`, `formname`.
- **Problem:** `$pid` normally comes from the session. Because this file runs in `custom_report.php`'s global scope, adding `ptid=NNN` to that request silently replaces the session patient for the rest of the report. That includes demographics, history, notes, and other forms.
- **Effect:** Any user can read another patient's chart by changing a URL parameter (an IDOR).
- **Fix:** Remove these assignments, or confine them to a dedicated entry point that performs an ACL check and stores values in local variables.

### 2. Variable-variables from the prefs table in global scope — High
- **Location:** `$$LOCATION = text($prefs['GOVALUE']);`
- **Problem:** Each `LOCATION` value from `form_eye_mag_prefs` becomes a global variable inside `custom_report.php`. It could overwrite `$pid`, `$PDF_OUTPUT`, `$printable`, `$encounter`, `$N`, and so on.
- **Other issues:**
  - The prefs appear unused in this file.
  - Applying `text()` at assignment time means values get double-encoded if they are echoed through `text()` later.
- **Fix:** Remove the block, or put the prefs into an array.

### 3. Drawing lookup can show another patient's image — High (PHI leak)
- **Location:** `display_draw_image()`, `"SELECT * from documents where documents.url like '%".$filename."'"`.
- **Problems:**
  - **Leading `%`:** For pid=1 / encounter=1, `%1_1_OU_EXT_VIEW.jpg` also matches `11_1_OU_EXT_VIEW.jpg` (patient 11).
  - **Unescaped `_`:** In `LIKE`, `_` is a single-character wildcard, so it matches more than intended.
  - **No ownership filter:** There is no `foreign_id = pid` condition.
  - **Not parameterized:** The value is concatenated into the SQL string.
- **Fix:** Use a parameterized query with `foreign_id = ?` and an exact-match condition (or escape the `LIKE` pattern).
- **Also:** `$document_id > '1'` wrongly excludes document id 1.

### 4. Stored XSS: database fields echoed without escaping — High
The following are output unescaped:
- `$HPI1`
- `$CHRONIC2`, `$CHRONIC3`
- `$item['codetext']`, `$item['code']`, `$item['plan']`
- the `$PLAN` items and `$PLAN2`
- `$CTLOSVA`
- the `$MOTILITY_*` values
- `$note->get_note()`
- `$providerNAME` (in the PDF branch)
- `$from_file` and `$filetoshow` inside `src` attributes

Fixes:
- Wrap each in `text()` / `attr()`.
- For `plan`, escape first, then apply `nl2br`, instead of replacing newlines with raw `<br />` on unescaped data.

### 5. String-concatenated SQL — Low/Medium
- **Location:** `"select * from facility where id=" . $_SESSION['pc_facility']`.
- **Fix:** Use a bound parameter.

---

## Correctness

### 6. Short open tag can break every patient report — High
- **Location:** `<?` near the end of the CC2 block.
- **Problem:** On servers with `short_open_tag=Off`, this is a parse error.
- **Effect:** `custom_report.php` includes this file whenever any patient has an eye_mag form, so the error breaks the entire report.
- **Fix:** Use `<?php`.

### 7. The `choice` parameter can never be set — Medium
- **Location:** `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];`
- **Problem:** The condition checks `CHOICE` but reads `choice`. These are different keys, so `$choice` stays empty unless both are sent.

### 8. `choice == "narrative"` renders nothing — Medium
- **Location:** the final branch of `eye_mag_report()`, `else if ($choice != "narrative")`.
- **Problem:** The doc comment says narrative is the default display. Explicitly passing `narrative` currently outputs an empty report.
- **Fix:** Change the branch to a plain `else`.

### 9. Wrong motility value displayed for the left eye — Medium (clinical data error)
- **Location:** the left-eye motility table, bottom row.
- **Problem:** The row prints `$MOTILITY_LLIO` twice. The first cell should be `$MOTILITY_LRIO`.

### 10. Typos and wrong conditions hide clinical findings — Medium

| Condition in code | Problem / correction |
|---|---|
| `$ODNEARVA_1\|\|$WNEAROSVA_1` | Should be `$OSNEARVA_1`. |
| `$ODGONIO\|\|$OSDGONIO` | Should be `$OSGONIO`. |
| `if ($ODNPC or $OSNPC)` | These variables don't exist; the row then prints `$NPC`. Should test `$NPC`. |
| `$PAMODBA` | Typo for `$PAMODVA`. |
| Retina: `$ODDISC\|\|$OSDISC\|\|$ODCUP\|\|$ODMACULA\|\|$ODVESSELS\|\|$ODPERIPH` | OS-only findings (cup, macula, vessels, periphery) are never shown. |
| Additional data: `$GLAREODVA\|\|$CONTRASTODVA\|\|$ODK1\|\|$ODK2\|\|$LIODVA\|\|$PAMODBA` | Ignores OS-only values. |
| Refraction table: `$ODVA\|\|$OSVA\|\|...` | The wearing data lives in `$ODVA_1` etc., so an encounter with only a current Rx shows no refraction table. |

### 11. Autorefraction comments read an out-of-range index — Low
- **Location:** autorefraction block, `${"COMMENTS_$i"}` used after the `for` loop.
- **Problem:** At that point `$i == $count_rx + 1`, so this always reads an undefined variable. It looks like copy-paste; it should probably be an AR-specific comment field.

### 12. Debug output in the column header — Low
- **Location:** `xlt('Type').$count_rx`.
- **Problem:** The Rx count is appended to the column header.
- **Also:** The header row has 10 columns while the title row uses `colspan="9"`.

### 13. Wrong form shown when an encounter has multiple eye_mag forms — Medium
- **Location:** `extract()` of query results in `eye_mag_report()` and `narrative()`.
- **Problems:**
  - Both queries filter by encounter only, not `form_id`, so with multiple eye_mag forms in one encounter an arbitrary one is shown.
  - The query in `eye_mag_report()` doesn't exclude deleted forms.
  - `narrative()` doesn't join `forms.pid`.
  - `extract()` can overwrite local variables and parameters (`$pid`, `$encounter`, `$form_id`, `$cols`, `$choice`) with column values.
  - If no row is found, the `@` suppresses the error and `new DateTime(null)` prints **today's** date as the visit date.
- **Fix:**
  - Query by `forms.form_id`.
  - Use `EXTR_SKIP` or explicit array access.
  - Handle the no-row case.

### 14. Translation and markup bugs — Low
- `<?php xla('...') ?>` (Red Desaturation title) is missing `echo`.
- `xlt('sc Near{{without correction near')` is missing the closing `}}`.
- `$css_header` and `$display_Add` are undefined inside `narrative()`, producing an empty stylesheet link and a notice.
- `$bad` and `$IMPPLAN_items` are uninitialized; the `foreach` over `$IMPPLAN_items` warns when there are no rows.
- `heght` typo in an `img` attribute (inside commented code).

---

## Maintainability

### 15. Dead code — Low
- `left_overs()` references undefined `$table_name` and `$id`.
- `full_report()` starts with `return;`, so the rest is unreachable.
- The large commented-out `DRAW` block should be removed.

### 16. Duplicated code — Low
- The document path-resolution code is copy-pasted three times (patient photo, `display_draw_image`, and `custom_report.php`).
- The HPI field blocks are duplicated per complaint and could be a loop.
- `report_ACT()` uses raw `htmlspecialchars` instead of the project's `text()` helpers.

### 17. Fragile inline output — Low
- Inline styles and the per-RX dynamic variables (`${"ODSPH_$count_rx"}`) make the template hard to follow.
- An array of rows would be clearer and safer.

---

**Recommendation:** Request changes. Items 1–4 and 6 should block merge. Items 7–10 and 13 are clinical-display correctness bugs that should also be fixed before release.