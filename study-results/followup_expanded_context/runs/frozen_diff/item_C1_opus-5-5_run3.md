# Code Review: `C_Document::retrieve_action()` — new `$disable_exit` parameter

## 🔴 Critical

### 1. Non-encrypted downloads of original files are likely to return empty content
**Location:** original-file branch (~line 513)

The `fopen` and `fread` calls were moved above the `if ($doEncryption)` check. The file is now read to EOF on every request, not just encrypted ones. The non-encrypted `else` branch is not shown in this diff. In upstream OpenEMR it serves the file using the same handle:

```php
header("Content-Length: " . filesize($url));
fpassthru($f);
```

If this file does the same, the pointer is already at EOF. `fpassthru` will then output 0 bytes while `Content-Length` advertises the full size. **Every normal, unencrypted document download would break.**

**Fix:** Do not consume the handle shared with the normal path. For example:

```php
if ($disable_exit) {
    return file_get_contents($url);
}
$f = fopen($url, "r");
```

Alternatively, call `rewind($f)` before `fpassthru`.

## 🟠 High

### 2. Large files are now always fully loaded into memory
**Location:** same block

Even when this does not cause empty output, every download now buffers the whole file in PHP memory. Previously, only encrypted downloads did this. Large scans and PDFs can exceed `memory_limit`.

### 3. Zero-byte and unreadable files now error on the normal path
**Location:** same block

- **Empty files:** `fread($f, 0)` raises a warning in PHP 7 and throws a `ValueError` in PHP 8. This now affects all downloads, not just encrypted ones.
- **Unreadable files:** `fopen` failure is not checked, so `fread(false, …)` errors too.

### 4. `$disable_exit` may be controllable from the request
**Location:** method signature

OpenEMR's `Controller::act()` maps query-string arguments onto action parameters positionally/by name. It also appends the action's return value to the page output, which is then echoed. A URL that adds `disable_exit=1` (or similar) could therefore:

- **Bypass encryption.** The `$doEncryption`/passphrase handling is skipped entirely, so plaintext is returned even when the user requested encryption.
- **Bypass headers.** Raw content is echoed without `Content-Type` or `Content-Disposition`, which raises content-sniffing/XSS risk for HTML or SVG uploads.

The `== true` comparison makes this worse. The string `"false"` is truthy, so `disable_exit=false` from a URL would *enable* the mode.

**Fix:**
- Move the internal-retrieval logic into a separate non-action method, for example `get_document_content($document_id)`, that the action and internal callers both use. This is the preferred option.
- At minimum, use a strict `=== true` check so string input cannot activate it.

## 🟡 Medium

### 5. Converted-file branch returns `null`
**Location:** ~line 554

```php
if($disable_exit == true) { return ; }
```

For `$original_file=false`, callers get nothing instead of the converted file's contents. This is inconsistent with the other two branches. If callers check the return value, it will look like an empty document. The branch should either return the contents of `$url` or fail explicitly.

### 6. File handle leak
**Location:** ~line 516

The early `return $filetext;` never calls `fclose($f)`.

### 7. Error paths still `die()`
**Location:** CouchDB failure, missing file, etc.

Programmatic callers using `$disable_exit=true` will have their whole request killed on error instead of receiving `false` or an exception. This defeats the purpose of the flag.

### 8. Inconsistent semantics across storage backends
The CouchDB path returns decoded content. The filesystem path returns raw content. The converted path returns `null`. Encryption is silently ignored in every case. This contract should be documented in a docblock, or unified behind a single helper.

## 🔵 Low / Maintainability

- **Indentation:** The new lines use spaces in a file indented with tabs, so the nesting is misleading (e.g., the new block at line 433 looks outside its `if`).
- **Comparison style:** `$disable_exit == true` should just be `if ($disable_exit)`, or `=== true` per #4.
- **Parameter order (pre-existing, worth noting):** A required parameter (`$document_id`) follows an optional one (`$patient_id=""`). Adding another trailing optional parameter grows an already awkward signature, and PHP 8 emits a deprecation for this.
- **Naming:** "disable_exit" describes a side effect rather than intent. A name like `$return_content` is clearer, though a separate method (see #4) is better still.

## Summary

I would request changes. The reordering of `fopen`/`fread` likely breaks standard unencrypted downloads (#1). The request-controllable flag (#4) can bypass encryption and response headers. I recommend extracting a dedicated, non-action content-retrieval method rather than threading a flag through this action.