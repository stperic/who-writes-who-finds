## Review Comments

**Location:** `interface/billing/sl_eob_process.php`, new `$eraDir` / `mkdir` block

1. **Partial migration from `$GLOBALS` to `OEGlobalsBag`**
   Only this one usage of `$GLOBALS['OE_SITE_DIR']` was converted to the new `OEGlobalsBag` accessor. If the rest of the file (or related billing code) still reads `$GLOBALS['OE_SITE_DIR']` directly, you now have two different access patterns for the same configuration value in the same codebase/file. This is confusing and increases the risk of future inconsistency (e.g., if `OEGlobalsBag` and `$GLOBALS` ever diverge).
   **Severity:** Medium (maintainability)

2. **No validation that `OE_SITE_DIR` is non-empty**
   If `OEGlobalsBag::getString('OE_SITE_DIR')` returns an empty string (missing key / bag not populated), `$eraDir` becomes `"/documents/era"` — an absolute path rooted at the filesystem root rather than the intended site directory. The code would then attempt to `mkdir` under `/`, which will likely fail in production (permission denied) but could succeed in misconfigured/dev/container environments, writing PHI-bearing ERA files to an unintended location.
   **Severity:** Medium–High (correctness/security)

3. **Directory permissions `0755`**
   The ERA directory stores billing/EOB files which contain PHI. `0755` makes the directory world-readable/executable (anyone on the host with filesystem access can list/traverse it, subject to umask and web server user). Confirm this matches the permission model used elsewhere for `documents/` subdirectories (many are created with more restrictive modes, e.g., `0700`). If not matched, this is a regression in data protection posture.
   **Severity:** Medium (security)

4. **Error message leaks server filesystem path**
   `die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'")` outputs the absolute server path to the end user. While `text()` correctly escapes it, exposing internal filesystem layout in an error message is an information-disclosure concern, however minor.
   **Severity:** Low

5. **Abrupt `die()` without logging**
   On failure to create the directory, the script simply `die()`s with a user-facing message. There's no `error_log()`/audit entry recording the failure, which will make diagnosing recurring permission/storage issues harder in production.
   **Severity:** Low

6. **Race-condition handling is fine, but worth a comment**
   The `!is_dir() && !mkdir() && !is_dir()` double-check pattern correctly handles concurrent creation races, but it's a subtle idiom — a short comment would help future maintainers understand why the second `is_dir()` check is needed.
   **Severity:** Low (nitpick)

No issues with the author/copyright header additions.