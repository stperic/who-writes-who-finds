# Review: `interface/billing/sl_eob_process.php`

## 1. Path traversal via `$eraname` (High, security, existing code this change relies on)

**Location:** the new `$nameprefix = "$eraDir/$eraname";`, plus the earlier `$eraname = $_GET['eraname'];`

**Problem:**
- `$eraname` comes straight from the query string. It is only checked for being non-empty.
- It is then put into a filesystem path. This PR rewrites that line but keeps the untrusted input.
- The path is used in two ways:
  - **Read:** `$nameprefix.edi` is opened and parsed. A value like `eraname=../../../../some/dir/file` reads any `*.edi` file the web server can access.
  - **Write:** when not in debug mode, the HTML report is written to `"$nameprefix.html"` with `fopen(..., 'w')`. An attacker can create or overwrite `.html` files anywhere the web server can write. That includes web-accessible directories, which gives stored XSS or phishing pages under the application's origin. It can also clobber existing files.
- The value is also built upstream in `sl_eob_search.php` from ERA file contents (GS date, ISA control number, payer ID). So a crafted 835 upload is a second way to inject path characters.

**Fix:**
- Validate `$eraname` against a strict allowlist, for example `/^[A-Za-z0-9_\-]+$/`. Alternatively, apply `basename()` and reject the value if it changed.
- After building the path, check that `realpath(dirname($eraFilePath))` equals `realpath($eraDir)`.

## 2. Directory created as a side effect, even in no-update/debug mode (Low–Medium, reliability)

**Location:** the new `mkdir($eraDir, 0755, true)` block

**Problem:**
- The ERA `.edi` file is supposed to have been moved into this directory already, at upload time in `sl_eob_search.php`.
- If the directory doesn't exist, the file can't exist either. Creating the directory here just hides the real problem, and processing then fails later with a less clear error.
- It also creates directories on a request that may be a debug/no-update run, which the surrounding comment says should not save anything.

**Fix:**
- Either fail with a clear "ERA file not found" error, or check that `$eraFilePath` exists.
- If the directory really must be created here, do it only on the `!$debug` path, where the report is actually written.

## 3. Full filesystem path disclosed in the error message (Low, security)

**Location:** `die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");`

**Problem:** This shows the absolute server path, including the site directory, to the browser.

**Fix:** Log the path with `error_log` or `SystemLogger`, and show the user only a generic message.

## 4. Undefined index on `$_GET['debug']` (Low, maintainability, touched context)

**Location:** `$debug = $_GET['debug'] ? 1 : 0;`

**Problem:** This raises an "undefined array key" warning on PHP 8 when the parameter is missing.

**Fix:** Use `!empty($_GET['debug'])`.

## 5. Inconsistent globals access (Nit)

**Problem:** This line now uses `OEGlobalsBag`, while the rest of the file still uses `$GLOBALS['OE_SITE_DIR']` and similar.

**Fix:** That's acceptable as an incremental migration, but consider converting the other `OE_SITE_DIR` uses in the file for consistency.

## Summary

The main blocker is issue 1. The PR touches the exact line that builds a file path from unvalidated user input, and that path is used for both reading and writing files. `$eraname` should be validated as part of this change.