# Review of `interface/forms/eye_mag/report.php`

## Security

**1. Request parameters override the patient and encounter with no authorization check (High)**
- Location: top-level, `if ($_REQUEST['ptid']) $pid = ...; encid; formid; formname`.
- Any logged-in user can pass `ptid`, `encid` or `formid` and read another patient's chart.
- Nothing verifies that the user is allowed to see that patient or encounter, and there is no ACL check.
- `formname` also overrides `$form_name` from the request.
- The values are not cast to int or validated.

**2. SQL injection in `display_draw_image()` (High)**
- Location: `$sql = "SELECT * from documents where documents.url like '%".$filename."'"`.
- `$filename` is built from `$pid` and `$encounter`, which come straight from `$_REQUEST`.
- Use bound parameters.
- The query is also not scoped to the patient (`foreign_id`), so `like '%...'` can match the wrong document.
- Also in `narrative()`: `"select * from facility where id=" . $_SESSION['pc_facility']` is concatenated. It is lower risk, but it should be bound.

**3. Stored XSS through unescaped output (High)**
Many DB-sourced fields are echoed without `text()`:
- `$HPI1`, `$CHRONIC2`, `$CHRONIC3`.
- `$item['codetext']`, `$item['code']`, `$item['codetype']`, `$item['plan']`. `plan` only has newlines replaced with `<br />`.
- `$PLAN` items and `$PLAN2`.
- `$note->get_note()`.
- `$CTLOSVA`.
- `$MOTILITY_*`.
- `$providerNAME` in the PDF signature branch.
- `$form_folder` in the `img src` attributes.
- Image `src` values built from file paths.
- Escape everything with `text()` or `attr()`. If line breaks are wanted, escape first and then apply `nl2br`.

**4. Variable injection through `$$LOCATION`, `@extract()` and `$$key` (Medium)**
- `$$LOCATION = text($prefs['GOVALUE'])` creates variables named from DB column values at global scope, so it can clobber `$pid`, `$encounter` and others.
- `@extract($encounter_data)` and `@extract($objQuery)` overwrite local variables such as `$pid`, `$encounter`, `$form_id`, `$cols` and `$choice`. The `form_encounter.*` and `form_eye_mag.*` columns collide (for example `id`, `pid`, `date`).
- `@` hides notices. Use explicit array access.

## Correctness

**5. Wrong request key for `choice` (High)**
- `if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];` checks `CHOICE` (upper case) but reads `choice`.
- PHP array keys are case-sensitive, so `choice` is almost never set and DRAW/TEXT never work as intended.

**6. Report-selection logic contradicts its own docs (Medium)**
- The comment says no choice or "narrative" shows everything.
- The code uses `else if ($choice != "narrative")`, so an explicit `narrative` choice renders nothing.
- The `DRAW` branch compares in upper case while the commented-out code uses `drawing`.

**7. Typos and wrong variable names (Medium)**
- `$ODNEARVA_1||$WNEAROSVA_1`: `$WNEAROSVA_1` is a typo.
- `$ODGONIO||$OSDGONIO`: `$OSDGONIO` is a typo.
- `$ODNPC or $OSNPC` is used, but only `$NPC` is checked in the outer condition.
- The OS motility table prints `$MOTILITY_LLIO` twice. The bottom-left cell should be `LRIO`.
- `$ODKTHICKNESS` and `$ODK2AXIS` should be checked against the schema.
- The `$ODVA` / `$OSVA` condition for the refraction table looks inconsistent with the other `$..._1` names.
- `xlt('Type').$count_rx` is leftover debug output that appends the count to the header.

**8. Stale loop variables and unset variables (Medium)**
- In the autorefraction block, `${"COMMENTS_$i"}` reuses `$i` after the loop ended. It prints the last RX comment again, or an undefined variable if `$count_rx` is 0.
- `$bad` is incremented without initialization.
- `$IMPPLAN_items` is undefined when there are no rows, so `foreach` raises a warning.
- `$css_header` is not declared `global` in `narrative()`.
- `$RX_TYPE` is stale or undefined for unknown RX types.
- `$display_Add` is undefined.
- `$web_root` is declared global in `display_draw_image()`, but `$GLOBALS['webroot']` is used elsewhere.

**9. PHP 7 incompatibility (Medium)**
- `($$zone[$i] >= '1') ? ($$zone[$i] = "-".$$zone[$i]) : ...` changes meaning in PHP 7. It is parsed as `${$zone}[$i]` instead of `${$zone[$i]}`.
- Use `${$zone[$i]}`, or better, an array.

**10. Missing `echo` (Low)**
- `<span title="<?php xla('Variation in red color...'); ?>">` never outputs the title.

**11. `display_draw_image()` problems (Low)**
- `$document_id > '1'` should be `> 0`.
- A computed `$to_file` is never used.
- The `$fname`, `$extension` and `$couch_*` variables are largely unused.
- The `blahblah=rand()` cache-buster is a hack.
- PDF mode emits server filesystem paths into `<img src>`.

## Maintainability and HTML

**12. Broken or fragile HTML structure (Medium)**
- In the ACT section a `</tr><tr>` sits inside `if ($ACT5CCDIST) {...}`, which produces unbalanced tables when blocks are missing.
- The Fields and Pupils `<td>` / `</td>` tags are conditionally opened and closed inconsistently.
- `style="report_vitals" style="..."` has a duplicated attribute.
- Short open tags (`<?`) are used. They break on servers with `short_open_tag` off.
- A stray `echo "\n ";` appears in the output.

**13. Dead and unused code (Low)**
- `left_overs()` uses undefined `$table_name` and `$id`.
- `full_report()` returns immediately.
- There are large commented-out blocks and a `$choice !== 'TEXT'` block that is empty.

**14. Other maintainability issues (Low)**
- `<link>` and `<style>` tags are emitted inside the function, so they repeat when the report is rendered multiple times on a page.
- Relative paths like `../../forms/...` are fragile.
- Some strings are not translated: `Comments:`, `Orders/Next Visit:`.
- Mixed `xlt` / `text` usage and a 2000-line mix of PHP and HTML make this hard to maintain. Move the data fetching and rendering into separate helpers.
- The file lacks a trailing newline, and the closing `?>` is unnecessary.