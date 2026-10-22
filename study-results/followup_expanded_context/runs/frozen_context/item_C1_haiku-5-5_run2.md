## Review of `retrieve_action` changes (`C_Document.class.php`)

### 1. `disable_exit` is reachable from the URL (High, security)

`act()` builds `$args_array` from every query-string parameter that is not reserved. Any extra parameter such as `&disable_exit=1` is therefore passed straight into `retrieve_action()`.

When the flag is set, the function returns raw file content without calling the header-setting code. Nothing forces a `Content-Type` or `Content-Disposition: attachment` header. The browser may then render an uploaded HTML or SVG document inline on the application's origin, which is a stored XSS vector. The ACL checks that run earlier in the method are not bypassed, but the response-shaping behavior is now client-controlled.

Fix: do not expose this as a request-controllable argument. Make it an internal-only flag, for example by calling a separate helper method that returns the content, or by setting a property on the object that the URL cannot reach. If it stays a parameter, at minimum force the download headers before returning.

### 2. Likely empty download for unencrypted files (High, correctness)

In the `original_file` branch, the diff moves `fread($f, filesize($url))` above the header block and out of the `$doEncryption` branch. That leaves the file pointer at EOF. If the unencrypted path still streams with `fpassthru($f)` or a similar read (not shown in the hunk), it will now send an empty body. Please verify that the non-encrypted path reads from the in-memory `$filetext` or rewinds with `rewind($f)`.

### 3. Resource and error handling in the `original_file` branch (Medium, reliability)

- `fopen($url, "r")` is no longer checked for `false`. A missing file now produces `fread`/`filesize` warnings and a broken response, and it happens before the headers are sent.
- The whole file is read into memory even when it is only being streamed. For large documents this is a memory regression compared with `fpassthru`.
- I could not see an `fclose($f)` in the changed hunks. If none exists in the untouched code, the handle leaks.

### 4. CouchDB branch returns before encryption handling (Medium, correctness)

The `return base64_decode($content);` is placed before any code that might apply `$doEncryption`/`passphrase` to the CouchDB content. If encryption is expected on that path, callers using `disable_exit` would receive plaintext or differently processed content. Confirm the intended behavior.

### 5. Ambiguous return contract (Low, maintainability)

The function returns file content, `null`, or (via `act()`) the concatenated output, depending on the flag and the branch. The `return ;` in the converted-file branch returns `null`, which callers may not expect. Document the return contract or use a dedicated method.

### 6. Style (Low)

The new lines mix spaces and tabs with the surrounding tab-indented code, and the `== true` comparisons could be `if ($disable_exit)`. The function signature also places a defaulted parameter before a required one (`$patient_id=""` before `$document_id`), which is pre-existing but worth noting.

### Summary

The most serious problems are #1 (URL-controllable flag that can lead to inline rendering of uploaded content) and #2 (possible empty downloads). Both should be resolved before merge.