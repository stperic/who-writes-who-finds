# Code Review: `C_Document::retrieve_action` — new `$disable_exit` parameter

## 1. Normal (unencrypted) downloads now return an empty body — **High (correctness regression)**

**Location:** the `if ($original_file)` branch, around new lines 513–524.

The PR moves `fopen()` and `fread($f, filesize($url))` so they run unconditionally, before the headers. Previously `fread` ran only inside `if ($doEncryption)`.

In the non-encryption path further down (not shown in the diff), the handle `$f` is streamed to the client, e.g. with `fpassthru($f)`. Because the whole file has already been read, the file pointer is at EOF. `fpassthru` therefore outputs nothing.

The result is that every ordinary document download serves an empty or truncated response, probably still with a `Content-Length` header for the full size.

**Fix:** keep the original flow for the download path. Either:
- read the file only when `$disable_exit` or `$doEncryption` is set, or
- call `rewind($f)` before streaming, or
- in the `$disable_exit` case, use `file_get_contents($url)` and leave `$f` untouched.

## 2. `$disable_exit` can be set from the URL — **High (security / behaviour)**

**Location:** the new signature, line 387, together with `Controller::act()`.

`Controller::act()` builds `$args_array` from the query string and passes it to the action with `call_user_func_array`. On PHP < 8, that associative array is passed positionally. So a request like this sets the new parameter:

```
controller.php?document&retrieve&patient_id=1&document_id=2&as_file=1&original_file=1&disable_exit=1
```

The parameter name in the URL doesn't even matter; any fifth argument will do.

Consequences:
- The raw file contents are returned and echoed through the controller output path without download headers.
- On the encrypted path, the plaintext is returned (see issue 3).
- Any existing URL that already passes a fifth argument will silently change behaviour.

Also note that the loose comparison `$disable_exit == true` treats any non-empty string, including `"false"`, as true.

**Fix:** don't expose this as an action parameter. Move the "get document content" logic into a separate non-action method, e.g. `retrieve_content()` or a method on the `Document` class, and have both `retrieve_action` and internal callers use it.

## 3. Encryption is bypassed when `$disable_exit` is true — **Medium–High (security)**

**Location:** the early `return $filetext;` at line 516. It sits before the `if ($doEncryption)` block.

If the request set `encrypted`/`passphrase` in POST, the caller receives plaintext anyway. The CouchDB branch (line 433) has the same problem: it returns `base64_decode($content)` before any encryption handling.

At a minimum this should be documented. Preferably, the content-retrieval helper should be clearly separated from the user-facing, encryption-aware download path.

## 4. Converted-file branch returns `null` — **Medium (correctness)**

**Location:** lines 554–556, `if($disable_exit == true) { return ; }`.

For non-original (converted) files, a caller asking for content gets `null`, and nothing tells them the request wasn't honoured. This is inconsistent with the other two branches, which return the file contents.

**Fix:** either return the converted file's contents, e.g. `file_get_contents($url)`, or fail explicitly.

## 5. Unchecked `fopen`/`fread`, empty files, and memory use — **Medium (reliability)**

**Location:** lines 513–514.

- **No error check:** if `fopen` returns `false`, the code proceeds with warnings and returns `false` or an empty string.
- **Empty files:** for a zero-length file, `fread($f, 0)` raises a warning ("Length parameter must be greater than 0") on PHP < 8 and an error on PHP 8.
- **Memory:** the whole file is now loaded into memory on every download, even when it is simply being streamed. That is a regression for large documents.

## 6. File handle leaked on early return — **Low**

**Location:** line 516.

`$f` is never closed when returning early. Use `file_get_contents`, or call `fclose($f)` before returning.

## 7. Download/audit logging is skipped — **Low–Medium (compliance)**

The early returns bypass whatever logging happens on the normal download path. In a medical records system, programmatic access to document contents should probably still be audit-logged.

## 8. Style / maintainability — **Low**

- The new lines use space indentation, while the surrounding code uses tabs and mixed styles. This makes the already confusing control flow harder to follow.
- `== true` is redundant; if the flag is kept, use `if ($disable_exit)` or a strict check.
- The name `$disable_exit` is misleading. The flag really means "return content instead of sending it". Something like `$return_content` would be clearer.
- Pre-existing: an optional parameter (`$patient_id=""`) comes before a required one (`$document_id`). Adding another parameter to this signature makes it worse; this supports the refactor into a dedicated helper suggested in issue 2.

## Summary

| # | Issue | Severity |
|---|-------|----------|
| 1 | File pointer consumed before streaming → empty downloads | High |
| 2 | `$disable_exit` controllable via URL through `Controller::act` | High |
| 3 | Early return bypasses encryption | Medium–High |
| 4 | Converted-file branch returns `null` | Medium |
| 5 | No error handling; empty-file `fread` warning; whole file in memory | Medium |
| 6 | File handle not closed | Low |
| 7 | Audit logging skipped | Low–Medium |
| 8 | Naming, indentation, loose comparison | Low |

**Recommendation:** request changes. Extract the content retrieval into a separate internal method rather than overloading the routed action with a flag.