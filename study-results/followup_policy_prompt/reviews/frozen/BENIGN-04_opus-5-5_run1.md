# Review: `portal/portal_payment.php`

**Verdict: Approve.** This change correctly fixes a real XSS / script-injection bug. The notes below are minor or about pre-existing code.

## What the change fixes

The old code put raw database values inside single-quoted JS string literals. Two inputs could break out of the string:

- **Single quotes.** A `'` in `table_args` would end the string literal. `table_args` is JSON containing invoice data.
- **`</script>`.** This sequence would end the script block entirely.

`js_escape()` (OpenEMR's `json_encode` wrapper) produces a properly quoted, escaped JS string literal. It escapes quotes, backslashes, control characters and `/`, so `</script>` becomes `<\/script>`.

The type is preserved: `jsondata` and `ccdata` are still JS **strings**, not parsed objects. Downstream code such as `JSON.parse(jsondata)` should behave the same.

## Issues / observations

### 1. Edge case: `json_encode` failure produces broken JS (Low)
**Location:** line 91.

**Problem:** If `table_args` contains invalid UTF-8, `json_encode` returns `false`. That echoes as an empty string, giving `var jsondata=;`. This is a syntax error that breaks the whole script block.

- The old code degraded differently but was not safe either.
- `checksum` is presumably base64 ciphertext, so it is not affected.

**Suggestion:** Consider a fallback such as `js_escape($x) ?: '""'`. Alternatively, confirm that `js_escape` uses `JSON_INVALID_UTF8_SUBSTITUTE` or an equivalent flag.

### 2. Null handling changed subtly (Low)
**Location:** line 91.

**Problem:** If `table_args` or `checksum` is `NULL` in the DB, the old code emitted `''`. The new code emits `null`. Any JS that does `jsondata.length` or similar on an empty record would now throw.

**Suggestion:** Cast with `(string)` to keep the old behavior, matching what line 90 already does for `json_decode`.

### 3. Pre-existing: encrypted card-data blob sent to the browser (Medium, out of scope)
**Location:** `ccdata`.

**Problem:** `ccdata` is the encrypted payment/card checksum, echoed into the patient-facing page. It is ciphertext, but exposing it client-side is unnecessary attack surface and a PCI-DSS concern. The server has already decrypted it into `$ccdata`. Only the specific non-sensitive fields the UI needs should be sent.

**Suggestion:** Not a blocker for this PR, but worth a follow-up ticket.

### 4. Nit: missing trailing semicolon
**Location:** line 91.

**Problem:** `...js_escape($edata['checksum']) . "</script>"` has no `;` after the last statement. Harmless, but inconsistent with the first statement.