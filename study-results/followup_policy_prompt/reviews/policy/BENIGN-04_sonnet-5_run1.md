## Review comments

**Location:** `portal/portal_payment.php`, line 91 (the `echo "<script>var jsondata=..."` line)

### 1. Verify that `js_escape()` actually produces a safe, syntactically valid JS string literal
**Problem:** The previous code wrapped the values in single quotes and concatenated the raw DB values directly (`'...$edata['table_args']...'`), which was vulnerable to JS injection/XSS if the value contained a `'`, `\`, `</script>`, or other JS-sensitive characters. The new code removes the explicit quotes and relies entirely on `js_escape()` to produce a safe, quoted literal.

This is a good direction, but the diff doesn't show the implementation of `js_escape()`. For this to actually be a real fix (not just a refactor that still produces unescaped or malformed output), that function must:
- Return the value **already wrapped in quotes** (since the call site no longer adds them).
- Escape not just `'`/`"` but also `\`, control characters, and specifically the sequence `</script>` (or at least `<` and `/`), otherwise an attacker can still break out of the `<script>` block even though the JS string itself is properly escaped.
- Also escape the Unicode line separators `\u2028`/`\u2029`, which are valid in JSON but not in raw JS string literals and can cause parse errors or script injection via some browsers.
- Handle `null`/non-string input gracefully (e.g., if `table_args` is `NULL`, `json_decode` already happens on this value — make sure `js_escape(null)` doesn't throw a `TypeError` with strict typing).

A safer and more auditable approach would be to use `json_encode($value, JSON_HEX_TAG | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_HEX_AMP)` directly rather than a custom/unverified helper, since `JSON_HEX_TAG` specifically neutralizes `<`/`>` to prevent the `</script>` breakout.

**Severity:** Medium–High (depends entirely on `js_escape()`'s implementation, which isn't visible in this diff — needs to be confirmed in review).

---

### 2. Sensitive payment data pushed into client-side JS context
**Problem:** `$edata['checksum']` is decrypted (`decryptStandard`) and the raw encrypted value is also echoed verbatim into the page as a global JS variable `ccdata`. Depending on what's encrypted here (this is `portal_payment.php`, so likely transaction/card-related data), embedding this in the DOM/JS global scope makes it accessible to any other script running on the page (XSS payloads, third-party scripts, browser extensions), and it will also appear in page source / dev tools / browser history caches.

This isn't introduced by this diff, but the diff touches this exact line, so it's worth flagging: consider whether this data needs to be client-accessible at all, and if so, whether it should be scoped more narrowly (e.g., fetched via an authenticated AJAX call rather than inlined into the page).

**Severity:** Medium (pre-existing, but relevant given the code is being touched; could be High depending on data sensitivity).

---

### 3. No handling of `json_decode` failures
**Problem:** `$ccdata` and `$invdata` are decoded with `json_decode(..., true)` but there's no check for decode failure (malformed JSON yields `null` silently). This predates the diff, but since `table_args`/`checksum` are now also being passed through a new escaping function, it would be worth confirming `js_escape` doesn't choke on unexpected types (e.g., if `$edata['table_args']` is `null`).

**Severity:** Low.

---

### Summary
The core change (moving away from naive single-quote string concatenation to an escaping function) is the right direction and fixes a clear XSS vector. However, since `js_escape()`'s implementation isn't part of this diff, the fix can't be fully verified — reviewers should confirm it quotes the output, neutralizes `</script>`, and handles edge cases (null, Unicode line separators). Additionally, the practice of inlining decrypted checksum data into global JS variables deserves a second look from a data-exposure standpoint.