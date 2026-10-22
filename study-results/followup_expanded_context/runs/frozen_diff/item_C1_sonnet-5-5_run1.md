## Review findings

**1. High: regression in the normal file download path (`@@ -507,14 +510,17 @@`)**
The `fopen` and `fread` calls were moved out of the `if ($doEncryption)` block, so they now run on every download. The `fread` moves the file pointer to EOF. The unchanged `else` branch for non-encrypted downloads most likely streams the file with `fpassthru($f)`, though that code is outside the diff context, so please confirm it. If it does, it will now send an empty body, and every ordinary download breaks. The new feature is the reason for the move, but the default path (`$disable_exit = false`) must behave exactly as before. Fix this by reading the file only inside `if ($disable_exit)`, for example with `file_get_contents($url)`, or by calling `rewind($f)` before streaming.

**2. Medium: unconditional full-file read and resource handling (same hunk)**
- Every download now loads the entire file into memory, including large PDFs and images that were previously streamed. This risks `memory_limit` failures.
- `fopen` is not checked for failure. `filesize()` of 0 makes `fread($f, 0)` warn, and it throws a `ValueError` on PHP 8.
- The early `return $filetext` leaves `$f` unclosed.

**3. Medium: inconsistent return contract (`@@ -545,6 +551,9 @@`)**
- In the converted-image branch, `if ($disable_exit == true) { return ; }` returns `null` instead of the content. The caller cannot tell "no content" from "not supported", and the feature silently does not work for that branch.
- The `return` sits after `$url` is computed but before any file read, so it looks unfinished.
- Other branches are not handled at all, such as the encrypted-download path and the thumbnail and mime-type paths. They still emit headers or call `exit`, so `$disable_exit` does not reliably do what its name says.
- Document the return type (string, `null`, or output and exit), or return `false` explicitly on failure.

**4. Medium: CouchDB branch skips existing behaviour (`@@ -430,6 +430,9 @@`)**
- The early return bypasses the encryption option (`$doEncryption`). The caller gets plaintext even if `$_POST['encrypted']` is set. If that is intended, it needs a comment.
- It is unclear whether the download log entry (`document_upload_download_log`) is written before this return. The retrieval should still be audited when it is called internally.
- `base64_decode($content)` is not strict, so corrupt data is silently accepted. Consider `base64_decode($content, true)` and a check for `false`.

**5. Low: security and design**
- `retrieve_action` is a controller action reachable by request. Callers that use `$disable_exit = true` must do their own ACL and patient-ownership checks. The new internal-use mode returns raw PHI as a string, so the ACL check at the top of the function should be verified to run before it.
- The `$_POST` passphrase and encrypted flag are still read in the internal-call mode, which mixes request state into a programmatic API. A separate method such as `get_document_content()` would be cleaner than a flag that changes the function's behaviour.

**6. Low: style and maintainability**
- `$disable_exit == true` uses a loose comparison, so use `if ($disable_exit)`.
- Indentation is mixed (spaces versus the file's tabs), and the new code is misaligned with its surroundings.
- The new parameter follows an already awkward signature, a defaulted `$patient_id=""` before a required `$document_id`. Adding a fifth positional boolean makes call sites hard to read.
- There are no tests or documentation for the new mode.