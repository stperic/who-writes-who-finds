Reviewing just this hunk (the `js_escape()` implementation itself isn't in the diff, so some of this depends on what that function does):

- **`portal/portal_payment.php:91`** — Switching from raw string interpolation inside a JS string literal to `js_escape()` is the right direction (the old code was vulnerable to JS injection if `table_args`/`checksum` ever contained a `'`, `\`, or newline). **Correctness/Security, but can't fully verify**: since `js_escape()`'s implementation isn't shown, confirm it:
  - Escapes `</script>` (or at least `<` / `/`) — if it's a thin wrapper around `json_encode()` without `JSON_HEX_TAG`/`JSON_HEX_AMP`, a literal `</script>` inside the stored string would still terminate the `<script>` block early (HTML parsing happens before JS parsing), re-enabling XSS even though the JS-string-escaping itself is fixed. **High severity if unhandled.**
  - Itself emits the surrounding quotes (e.g. behaves like `json_encode`), since the call site no longer adds `'...'` around the value. If it returns an unquoted/raw string, this is a functional bug (invalid JS / silent XSS). **High if wrong, but likely fine if it mirrors `json_encode`.**
  - Handles non-UTF-8 or malformed input gracefully (if it's `json_encode`-based, invalid UTF-8 makes `json_encode` return `false`, which would print `jsondata=;`, a silent data-loss bug rather than a crash). **Low/Medium.**

- **Unchanged from before**: the code echoes the *raw* (still-encrypted/encoded) `$edata['table_args']` and `$edata['checksum']` into the page rather than the already-decoded `$invdata`/`$ccdata`, even though decoding happened right above. Not introduced by this diff, but worth asking why decode then discard — if intentional (client-side needs the raw blob), fine; otherwise it's dead work. **Low, pre-existing.**

- **Scope check**: worth confirming there aren't other `echo "<script>...'" . $foo . "'..."` patterns elsewhere in this file or others using the same unescaped pattern that should get the same `js_escape()` fix for consistency. **Informational.**

No other correctness/reliability issues in this hunk — the fix direction is sound, contingent on `js_escape()`'s actual implementation covering the `</script>` breakout case.
