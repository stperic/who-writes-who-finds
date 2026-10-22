# Code review: `C_Document::retrieve_action` `$disable_exit` change

## 1. Critical: normal (unencrypted) file downloads now return empty content

**Location:** `original_file` branch, around new lines 513–524.

The `fread()` call was moved out of the `if ($doEncryption)` block and now runs every time. In the existing code, the non-encryption `else` path serves the file with `fpassthru($f)` after setting `Content-Length: filesize($url)`.

Because the whole file has already been read, the handle is at EOF. `fpassthru()` therefore outputs nothing. The browser receives headers saying N bytes, followed by a zero-length body, so every plain document download is broken. That is the most common path.

**Fix:** only read the file into memory when it is needed:

```php
if ($disable_exit) {
    return file_get_contents($url);
}
$f = fopen($url, "r");
if ($doEncryption) { $filetext = fread($f, filesize($url)); ... }
```

Alternatively, call `rewind($f)` before `fpassthru()`. The first option is cleaner.

## 2. High: whole file is loaded into memory on every request

**Location:** same block.

Even after fixing #1 with `rewind()`, the current structure reads the entire document into memory before streaming it. Large scans, DICOM files or videos could hit `memory_limit`, which the old streaming path avoided. Reading into memory should be limited to the `$disable_exit` and encryption cases.

## 3. High: the converted-file branch returns `null` instead of content

**Location:** third hunk, where `return ;` was added.

When `$original_file` is false and `$disable_exit` is true, the method returns nothing. Callers expect document bytes and will silently get `null`. That could produce empty attachments, PDFs or faxes with no error raised.

The branch should either:
- return `file_get_contents($url)` for the converted file, or
- throw or log an explicit "unsupported" error.

## 4. Medium: `fopen` and `fread` results are not checked

**Location:** `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));`

- If the file is missing or unreadable, `fopen` returns `false`, and the method then calls `fread(false, …)`.
- `filesize()` may be `false` or `0`. `fread($f, 0)` raises a warning in PHP 7 and throws a `ValueError` in PHP 8.

On the `$disable_exit` path, the caller may get `false` or an empty string with no indication of failure. Errors should be checked and reported.

## 5. Medium: the new return paths skip the encryption logic

**Location:** CouchDB and filesystem return paths.

When `$disable_exit` is true, `$doEncryption` / `$passphrase` from `$_POST` are silently ignored and plaintext is returned. That is probably intended for internal callers, but it should be:
- documented, and
- made impossible to trigger from a request.

## 6. Medium: the new parameter may be reachable from request input

`retrieve_action` is invoked through `Controller::act()`, which maps query-string values onto action arguments in order. Please confirm a user cannot supply a fifth argument and flip `$disable_exit`.

At minimum, this would make the endpoint emit an empty 200 response. It could also bypass whatever download logging or encryption the normal path performs.

Safer options:
- move the "get content" logic into a separate, non-action method such as `get_document_content($document_id, …)`, or
- force the parameter to false when the method is called via dispatch.

This would also remove the awkward boolean flag (see #8).

## 7. Low: file handle is leaked on the early return

**Location:** `return $filetext;`

`$f` is never closed on this path. Use `file_get_contents()` or call `fclose($f)` before returning.

## 8. Low: maintainability and style

- **Flag argument:** adding a "return instead of output" flag to a method that already has a required parameter after an optional one (`$patient_id=""`, `$document_id`) makes the signature harder to use. Extracting a content-retrieval helper used by both the download action and internal callers would be cleaner, and would avoid duplicating the branching across three places.
- **Loose comparison:** `$disable_exit == true` should be `if ($disable_exit)` or `=== true`.
- **Indentation:** the new lines mix spaces into a tab-indented file and do not line up with the surrounding block.
- **Documentation:** there is no docblock describing the new parameter or what it returns in each branch.

## Summary

Issue #1 is a merge blocker: it breaks standard document downloads. Issues #3 and #6 should also be resolved before merging. The cleanest fix for #1, #2, #3, #6 and #7 together is to extract the content-retrieval logic into a separate non-action method.