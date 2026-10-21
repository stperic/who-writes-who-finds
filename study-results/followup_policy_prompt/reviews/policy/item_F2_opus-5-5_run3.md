# Review: `interface/billing/sl_eob_process.php`

## 1. Path traversal via `$eraname` (pre-existing, made reachable by this change)

**Severity: High (security)**

**Location:** `$nameprefix = "$eraDir/$eraname";` and every use of `$nameprefix` / `$eraFilePath` after it.

**Problem:**
- Earlier in the script, `$eraname` is taken directly from `$_GET['eraname']`. The only check is that it is non-empty.
- It is then joined into a filesystem path. That path is used to:
  - read the ERA file (`$eraFilePath`, passed to `parseERAForCheck()` and the main parse), and
  - write the report (`$nameprefix . '.html'`, opened for writing when not in debug mode).
- A value such as `../../../../etc/passwd%00` or `../../sites/default/sqlconf` lets an authenticated billing user read files outside `documents/era`.
- A value such as `../../../../var/www/html/x` writes an `.html` file containing partly attacker-influenced ERA content anywhere the web server user can write. That can be used for stored XSS or defacement.
- The new `mkdir(..., true)` makes the base directory always exist. This removes a failure mode that previously could stop the traversal on fresh installs.

**Fix:**
- Restrict `$eraname` to a strict whitelist, e.g. `preg_match('/^[A-Za-z0-9._-]+$/', $eraname)`, and reject anything containing `..` or `/`. Or use `basename()` plus that regex.
- Optionally, check that `realpath(dirname($eraFilePath)) === realpath($eraDir)` before any read or write.

## 2. Server filesystem path exposed in the error message

**Severity: Low (information disclosure)**

**Location:** `die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");`

**Problem:** The absolute site directory path is echoed to the browser. It is HTML-escaped, so this is not XSS, but it is unnecessary disclosure.

**Fix:** Log the full path with `error_log` / `SystemLogger` and show the user a generic message.

## 3. Directory is created even when nothing will be saved

**Severity: Low (correctness/maintainability)**

**Location:** The new `mkdir` block runs before `if (!$debug)`.

**Problem:** The comment says not to save in no-update situations, yet the directory is still created. This side effect is harmless, but the `mkdir` belongs with the write path. The read path (`parseERAForCheck`) only needs the file to exist.

**Fix:** Create the directory only inside the non-debug branch that writes files.

## 4. Inconsistent globals access

**Severity: Low (maintainability)**

**Problem:** This hunk switches to `OEGlobalsBag`, but the rest of the file still uses `$GLOBALS[...]`. That is fine as incremental migration. However, `getString('OE_SITE_DIR')` returning an empty string would yield `/documents/era`, and `mkdir` would then try to create it at the filesystem root.

**Fix:** Guard against an empty `OE_SITE_DIR`.

## 5. Unchecked superglobal (pre-existing)

**Severity: Low**

**Location:** `$debug = $_GET['debug'] ? 1 : 0;`

**Problem:** This raises an undefined-index warning when `debug` is absent.

**Fix:** Use `!empty($_GET['debug'])`.

## 6. Directory permissions

**Severity: Informational**

**Problem:** `0755` makes PHI-bearing ERA files' directory world-listable on shared hosts.

**Fix:** Consider `0750`/`0700`, or rely on the umask, consistent with other `documents/` subdirectories.

---

**Summary:** The directory-creation change itself is reasonable. However, the code it touches builds file paths from unsanitized `$_GET['eraname']`, which allows arbitrary file read and write. That should be fixed before or alongside this merge.