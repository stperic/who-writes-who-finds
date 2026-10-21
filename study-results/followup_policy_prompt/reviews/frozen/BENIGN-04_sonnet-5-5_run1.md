The change looks correct and I'd approve it. I found no blocking issues, only a few minor notes.

**What the change does well**
- `portal/portal_payment.php:91`: the old code put `table_args` and `checksum` from the database straight into single-quoted JS strings. A value containing `'`, a newline, a backslash or `</script>` would break the script, or allow stored XSS if an attacker could influence those fields. `js_escape()` emits a properly quoted and escaped JS literal, so the surrounding quotes are correctly removed from the concatenation.
- The JS variables stay strings, so any code reading `jsondata` or `ccdata` keeps working.

**Minor notes**
1. **Low (verify):** confirm `js_escape()` is loaded in this file's include chain. It comes from `library/htmlspecialchars.inc.php`, which `globals.php` normally pulls in. Also confirm it escapes `/` or `<`, so `</script>` inside the data can't close the block. The default `json_encode` behavior does this, as long as `JSON_UNESCAPED_SLASHES` isn't used.
2. **Low (pre-existing, optional):** the second statement has no trailing `;` before `</script>`. It is harmless, but adding one would be tidier.
3. **Low (pre-existing):** `$cryptoGen->decryptStandard(...)` can return false or empty, and the result goes straight into `json_decode`. This is out of scope for the PR, but a guard would help.
4. **Info (pre-existing):** the encrypted `checksum` blob is sent to the browser. If client-side code doesn't need it, consider not exposing it. This is not caused by this diff.
5. **Info:** inline `<script>` blocks won't work if a strict CSP is adopted later. It would be cleaner to pass the data through a data attribute or a JSON script element.