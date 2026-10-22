## Summary

This is a very large (2060-line) legacy-style report file that mixes business logic, DB access and presentation in a handful of giant functions. Beyond the general maintainability concerns, there are some concrete security and correctness bugs that should block merge or at least be fixed before release.

---

### 1. SQL Injection in `display_draw_image()` — **Critical**
```php
function display_draw_image($zone,$encounter,$pid){
  ...
  $base_name = $pid."_".$encounter."_".$side."_".$zone."_VIEW";
  $filename = $base_name.".jpg";
  $sql = "SELECT * from documents where documents.url like '%".$filename."'";
  $doc = sqlQuery($sql);
```
`$pid` and `$encounter` originate from `$_REQUEST['ptid']`/`$_REQUEST['encid']` and are passed straight through `eye_mag_report()` into this function, where they are concatenated directly into a SQL string instead of using a parameterized query (unlike almost every other query in this file, which correctly uses `sqlQuery($q, array(...))`). This is a clear SQL-injection vector reachable from user-controllable request parameters.

**Fix:** use `sqlStatement/sqlQuery` with placeholders, e.g. `sqlQuery("SELECT * from documents where documents.url like ?", array('%'.$filename))`.

---

### 2. Stored/Reflected XSS from unescaped DB output — **High**
Several places echo data pulled straight from the database (patient-entered free text) without passing through `text()`/`htmlspecialchars`, unlike the surrounding code which is otherwise careful to use `text()`:

```php
<b><?php echo xlt('HPI'); ?>:</b>   
&nbsp;<?php echo $HPI1; ?>              // not escaped (HPI2/HPI3 *are* escaped a few lines later)
...
echo $item['codetext']."<br />";       // IMPPLAN codetext, not escaped
echo $item['code']."<br />";           // IMPPLAN code, not escaped
echo $item['plan']."</div><br />";     // IMPPLAN plan text, only newline-substituted, not escaped
...
foreach ($PLAN_items as $item) { echo  $item."<br />"; }   // PLAN items, not escaped
if ($PLAN2) { echo $PLAN2."<br />"; }                      // not escaped
```
`$sanitize_all_escapes` only affects SQL escaping of inbound data, it does not HTML-escape output. If any of these fields can contain `<script>` or other markup (e.g., entered via another form or API), this becomes stored XSS.

**Fix:** wrap all of these in `text()` consistently.

---

### 3. Missing authorization / ACL check before rendering patient data — **High**
`acl.inc` is required, but `acl_check()` is never called anywhere in this file. Compare with `custom_report.php`, which explicitly checks `acl_check('encounters','notes')`, `acl_check('patients','med')`, etc. before showing clinical data. This report dumps full clinical exam data (HPI, refraction, retina findings, plan, signature images, patient photo) for an arbitrary `pid`/`encid` supplied via `$_REQUEST`, with no visible access-control gate in this file. If the caller doesn't enforce this elsewhere, this is an unauthorized PHI disclosure risk.

**Fix:** add an explicit ACL check for the current user/patient/encounter before producing output.

---

### 4. Logic bug: mismatched request key casing — **Medium**
```php
if ($_REQUEST['CHOICE']) $choice = $_REQUEST['choice'];
```
Checks `CHOICE` (uppercase) but reads `choice` (lowercase). Since PHP array keys are case-sensitive, this condition will basically always be false in normal use (callers send lowercase `choice`), so `$choice` never gets set via this branch — likely a typo that breaks the "mouseover" narrative/text/draw switching described in the docblock.

**Fix:** `if (!empty($_REQUEST['choice'])) $choice = $_REQUEST['choice'];`

---

### 5. Unsafe `@extract()` on query results — **Medium**
```php
$objQuery = sqlQuery($query,array($encounter,$pid));
@extract($objQuery);
...
$encounter_data = sqlQuery($query,array($encounter,$pid));
@extract($encounter_data);
```
`extract()` silently creates/overwrites local variables named after DB column names, including ones used for control flow elsewhere (`$choice`, `$PDF_OUTPUT`, etc., via globals leaking into local scope through `global` declarations). The `@` suppresses any warnings, hiding bugs if the schema changes or unexpected columns appear. This pattern, repeated with variable-variables throughout (`$$LOCATION`, `${"ODSPH_$i"}`, `$$zone[$i]`, `$$ODzone`), makes the code very hard to trace and reason about, and easy to accidentally shadow a security- or logic-relevant variable.

**Fix:** access fields explicitly (`$row['field']`) instead of `extract()`, and avoid dynamic variable names.

---

### 6. SQL built from session value without parameterization — **Low/Medium**
```php
if ($_SESSION['pc_facility']) {
  $sql = "select * from facility where id=" . $_SESSION['pc_facility'];
}
```
Even though this mirrors an existing pattern in `custom_report.php`, it's newly duplicated here. `$_SESSION['pc_facility']` should still be bound as a parameter rather than concatenated, as a defense-in-depth measure.

---

### 7. Dead/commented-out code & orphan function — **Low (maintainability)**
- A large commented-out block inside `eye_mag_report()` (the old `DRAW`/`drawing` implementation) should be removed rather than kept commented, especially since it contains stray short tags (`<?` without `php`) and a typo (`heght=75`).
- `left_overs()` is defined but never called anywhere, and references undefined `$table_name`/`$id`.
- `full_report()` immediately `return`s before doing anything — dead code kept "for reference." If it's truly unused, move to documentation/wiki rather than shipping it in production code.

---

### 8. Minor reliability/style issues — **Low**
- Mixed use of `<?php ... ?>` and bare `<?` short tags (in the commented block) — fragile if `short_open_tag` is off.
- `$bad` and `$RX_TYPE` are used without initialization before the loop (relies on PHP's implicit null-to-0/empty coercion); works but generates notices and is fragile if logic changes.
- File has no trailing newline (minor lint nit).
- Very large single-responsibility functions (`narrative()` is ~1500 lines) mixing query, business logic, and markup — hard to test or maintain; consider splitting into smaller render helpers.

---

## Recommendation
Items 1–3 are security-significant and should be fixed before merge. Item 4 is a functional bug that likely breaks the intended "choice" feature. Items 5–8 are maintainability/reliability concerns worth addressing but not necessarily blocking.