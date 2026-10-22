# Review: `interface/forms/eye_mag/report.php` (new file, ~2060 lines)

**Verdict: request changes.** The file has a SQL injection, a likely authorization gap, and widespread unescaped output. The rest is correctness bugs and maintainability problems.

---

## Critical / High

### 1. SQL injection in `display_draw_image()`
**Location:** `display_draw_image()`, the first query:
```php
$base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
$filename = $base_name.".jpg";
$sql = "SELECT * from documents where documents.url like '%".$filename."'";
$doc = sqlQuery($sql);
```
`$pid` and `$encounter` originate from `$_REQUEST['ptid']` and `$_REQUEST['encid']` and are never cast or validated. The query is built by string concatenation and run without bind parameters. An attacker can inject SQL through `encid`. This needs parameterized binding (`sqlQuery($sql, array(...))`) and should also cast `$pid`/`$encounter` to int or validate them.

### 2. No access control on the report
The file requires `acl.inc` but never calls an ACL check (for example `acl_check('patients', 'med')`). It also takes `pid`, `encid`, and `formid` straight from the request and uses them to load and render PHI (demographics, photos, notes, exam data). Nothing verifies that the current user may view that patient. If the parent page does not enforce this, any logged-in user can read any patient's eye exam by changing IDs. Please confirm this, and add an explicit check if it is missing.

### 3. Pervasive unescaped output (stored XSS)
Several values come from the database and are echoed without `text()`/`attr()`/`xlt()`:
- `echo $HPI1;` and `echo $HPI2` / `$HPI3`-style fields. The HPI is printed raw, while the other fields use `text()`.
- `echo "&nbsp;".$CHRONIC2."<br />";` and the `$CHRONIC1` / `$CHRONIC3` equivalents.
- Impression/plan: `echo $item['codetext']`, `echo $item['code']`, `echo $item['plan']`. The `plan` field is only newline-converted with `str_replace`, which does not escape HTML.
- Orders: `echo $item` from `explode('|', $PLAN)`, plus `echo $PLAN2`.
- Notes: `'<td>'.$note->get_note().'<br /><br /></td>'`.
- Attributes: `<img src='". $from_file."'`, `class="refraction <?php echo $display_Add; ?>"`, and `$background` inside a `style` attribute.
- `<?php echo ($CTLOSVA?:"-"); ?>` skips `text()` while the neighbouring fields use it.

Stored clinical text can contain markup, so this is a real XSS risk. Escape everything with `text()` or `attr()`, or sanitize at write time. Also note that `report_ACT()` is used for comments and is misnamed, since it does the same escaping as `text()`.

### 4. Variable-variable extraction from user preferences
```php
$query = "SELECT * FROM form_eye_mag_prefs where PEZONE='PREFS' AND id=? ...";
while ($prefs = sqlFetchArray($result)) {
  $LOCATION = $prefs['LOCATION'];
  $$LOCATION = text($prefs['GOVALUE']);
}
```
Any column value in this table becomes a global variable name at file scope. A row with `LOCATION` set to `pid`, `encounter`, `_SESSION`, or `GLOBALS` can overwrite critical state. Also, `text()` is applied at load time, so values are double-escaped if used in other contexts. Replace this with an explicit whitelist of expected keys.

### 5. `@extract()` on query results
```php
@extract($objQuery);
@extract($encounter_data);
```
These overwrite local variables (including `$pid`, `$form_id`, `$choice`) with whatever columns the query returns, and `@` hides the warnings. Both queries also select `form_eye_mag.*` and `form_encounter.*`, so column names can collide. Use explicit field access, or at minimum avoid `@`.

---

## Medium

### 6. Request parsing bugs
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
The check reads `CHOICE` but the assignment reads `choice`. Also, `$_REQUEST['x']` is read without `isset()` (undefined-index notices), and truthiness checks like `if ($_REQUEST['ptid'])` reject a legitimate value of `"0"`.

### 7. `narrative()` does not handle a missing encounter
If the query returns no row, `$encounter_date` is undefined, `new DateTime(null)` silently returns "now", and the report renders with the wrong date and no data. The function should check for an empty result and bail out with a message.

### 8. Motility grid is wrong
In the left-eye (`OS`) table, the rows are:
```
LRSO LS LLSO
LR   L0 LL
LLIO LI LLIO
```
`MOTILITY_LRIO` is never displayed and `MOTILITY_LLIO` is shown twice. The first cell of the last row should be `MOTILITY_LRIO`.

### 9. Other field-name bugs
- `ODNPC or OSNPC` is the condition, but the body prints `$NPC`.
- `if ($ODGONIO||$OSDGONIO)`: `OSDGONIO` looks like a typo for `OSGONIO`.
- `if ($ODNEARVA_1||$WNEAROSVA_1)`: `WNEAROSVA_1` looks like a typo for `OSNEARVA_1`, which would hide the OS near VA row.
- In the Red Desaturation row, `<span title="<?php xla('...'); ?>">` calls `xla()` without `echo`, so the title is empty.
- `<table style="report_vitals" ...>` puts a class name in the `style` attribute and duplicates the attribute.
- `$RX_TYPE` is not reset per iteration, so an unexpected `RX_TYPE` value silently reuses the previous row's label.
- `$bad` is used as a counter without initialization. This works in PHP, but it is fragile and triggers notices.
- `$ODVF`, `$OSVF`, and similar arrays are used before being defined for some paths.
- Labels such as `'Cyl{{Cyinder}}'` contain typos.

### 10. Inconsistent globals and paths
The file mixes `$GLOBALS['webroot']`, `$GLOBALS['web_root']`, `$GLOBALS["webserver_root"]`, and `$GLOBALS["webroot"]`. Some of these are presumably undefined, which produces broken image URLs in one mode or the other. Paths built from `$providerID` and `$pid` are also concatenated directly into filesystem and URL paths without validation.

### 11. Dead and misleading code
- `full_report()` returns immediately, so everything after `return;` is unreachable.
- `left_overs()` references `$table_name` and `$id`, which are undefined in that scope. It is never called.
- `eye_mag_report()` contains a large commented-out block.
- `$fake_register_globals` and `$sanitize_all_escapes` are set at the top but not used in this file.

---

## Low / Maintainability

- The file is about 2000 lines in a single function-based script, with the same clinical section (Refraction, ACT, Motility, and so on) repeated in markup. The ACT block alone is about 200 lines of near-identical tables. Consider data-driven rendering helpers.
- The same encounter query appears in `eye_mag_report()` and `narrative()`, with slightly different conditions (`forms.deleted != '1'` appears only in the second). That discrepancy could cause the summary and full views to disagree.
- Several hard-coded English strings (`'Orders/Next Visit:'`, `'Comments:'`, `'Timing'`-style labels) are not wrapped in `xlt()`, which breaks translation.
- The `Document` photo lookup and the display-image lookup duplicate the path-building logic.
- The file lacks a trailing newline, which is minor.

---

## Summary

| Severity | Issue | Location |
|---|---|---|
| Critical | SQL injection via `encid`/`ptid` | `display_draw_image()` |
| High | No ACL check on PHI | top-level / `narrative()` |
| High | Stored XSS from unescaped DB and note fields | `narrative()`, impression/plan loop, `display_draw_image()` |
| High | Prefs written to variable variables | top of file |
| Medium | `@extract()` clobbers state and hides errors | `eye_mag_report()`, `narrative()` |
| Medium | `CHOICE`/`choice` mismatch, no `isset` | top of file |
| Medium | Missing encounter not handled | `narrative()` |
| Medium | Motility grid omits LRIO, duplicates LLIO | `narrative()` |
| Medium | Wrong field names in conditions and output | multiple |
| Low | Dead code, inconsistent globals, untranslated strings | multiple |

Fix items 1–5 before merging. Items 6–11 should be addressed in the same PR or tracked as follow-ups.