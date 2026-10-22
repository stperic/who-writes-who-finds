# Code Review: `C_Document::retrieve_action()` adds a `$disable_exit` flag

## 1. The new parameter can be set from the URL, which bypasses encryption

**Location:** `retrieve_action(..., $disable_exit=false)`, together with `Controller::act()`
**Severity:** High (security)

`Controller::act()` builds `$args_array` from the query string. It then calls the action through `call_user_func_array`, which binds the values to parameters by position. The new parameter is therefore reachable from the web, for example:

```
controller.php?document&retrieve&patient_id=1&document_id=5&as_file=&original_file=1&disable_exit=1
```

The value `"1"` is loosely equal to `true`. The method then returns the raw file, and `act()` returns it as `$output`, which the front controller emits.

In both new early-return paths (CouchDB and filesystem), the return happens before the `$doEncryption` handling. A user who asked for an encrypted download, or any caller that relies on that flow, gets plaintext instead. The early return also skips the Content-* headers. Depending on code not shown in this diff, it may also skip `document_upload_download_log()` auditing of successful downloads. For PHI, that is an audit-trail gap.

**Recommendation:**
- Do not expose this as a positional action parameter.
- Move the "get document bytes" logic into a separate non-`_action` method, such as `get_document_content()`. Internal callers would use that method, and `retrieve_action` would use it for streaming.
- If the flag must stay, `act()` must not be able to set it. The early return should also respect encryption and logging.

## 2. File handle leak, and no check on `fopen` failure

**Location:** filesystem branch, `$f = fopen($url,"r"); $filetext = fread(...); if ($disable_exit) return $filetext;`
**Severity:** Medium

- When `$disable_exit` is true, the function returns without calling `fclose($f)`.
- The `fopen` result is never checked. If the file is missing or unreadable, `fread(false, ...)` emits warnings or errors, and the function returns `false` or garbage instead of reporting an error.
- `filesize()` returns 0 for empty files. `fread($f, 0)` raises a ValueError in PHP 8 and a warning in older versions.

**Recommendation:** Use `file_get_contents($url)` and check the result for `false`.

## 3. The whole file is now read into memory on every download

**Location:** same hunk. The `fread` was moved out of `if ($doEncryption)`.
**Severity:** Medium (performance and reliability)

Previously the full read happened only when encryption was needed. The plain-download path presumably streamed the file from `$f` (for example with `fpassthru`). Now every normal download first loads the entire file into `$filetext`. This happens even when `$disable_exit` is false and the content is then streamed again or never used.

For large documents such as scans or DICOM, this can exceed `memory_limit` and break downloads that used to work.

**Recommendation:** Read the full contents only when `$disable_exit` or `$doEncryption` requires it.

## 4. The converted-file branch returns `null`

**Location:** `if($disable_exit == true) { return ; }` in the `!$original_file` branch
**Severity:** Medium (correctness)

In the other two branches, the flag returns the document contents. Here it returns nothing, even though the converted file path `$url` has just been computed.

A caller that asks for content with `$original_file=false` silently gets `null`, so it might, for example, attach an empty document.

**Recommendation:** Return `file_get_contents($url)` here, with error handling. If this case is unsupported, fail explicitly.

## 5. Error paths still `die()` even with `$disable_exit`

**Location:** CouchDB failure path (`die(xl("File retrieval from CouchDB failed"))`), plus other existing `die`/`exit` calls in the method
**Severity:** Low–Medium

The flag is named "disable_exit", but failures still terminate the whole request. Programmatic callers cannot handle the error, and the caller's own response is cut off midway.

**Recommendation:** When in "return" mode, return `false` or throw an exception.

## 6. Smaller issues

**Severity:** Low (maintainability)

- **Naming:** `$disable_exit` describes a side effect, not what the flag does. The flag really means "return the content instead of streaming it". Something like `$return_content` would be clearer.
- **Loose comparison:** `$disable_exit == true` is satisfied by any truthy string from the URL, which feeds issue #1. Use `=== true` if a boolean is intended.
- **Inconsistent return types:** the method returns raw bytes, base64-decoded bytes, or `null`, depending on the branch. This should be documented, ideally with a single consistent return value.
- **Formatting:** the new lines use spaces while the surrounding code uses tabs, so the indentation is inconsistent and the diffs are hard to read.
- **Signature:** the optional `$patient_id=""` comes before the required `$document_id`, and this change adds more parameters after them. That pattern is deprecated in PHP 8 and makes the signature fragile.