## Review Comments

### 1. **Critical — `fread()` now consumes the file handle before the non-encryption path can use it**
**Location:** `controllers/C_Document.class.php`, inside the `if ($original_file)` block

```php
$f = fopen($url,"r");
$filetext = fread( $f, filesize($url) );
if($disable_exit == true) {
    return $filetext;
}
...
if ( $doEncryption ) {
    $ciphertext = $this->encrypt( $filetext, $passphrase );
    ...
}
```

Previously, `fread()` was only called inside the `$doEncryption` branch; the non-encryption branch presumably streams the file via `fpassthru($f)` using the still-at-offset-0 file pointer. Now `fread($f, filesize($url))` is called unconditionally and reads the file to EOF *before* the encryption check. When `$doEncryption` is false and `$disable_exit` is false, `$f`'s pointer is already at EOF, so any subsequent `fpassthru($f)` call will output nothing — **normal (non-encrypted) file downloads will be broken, returning empty content.**

**Severity: High/Critical** — regresses the main, most common code path (plain file download).

---

### 2. **Unconditional full-file read into memory**
**Location:** same block as above.

Every call to this path now loads the entire file into a PHP variable via `fread()`, even when the caller just wants the file streamed to the browser (`$disable_exit == false`, `$doEncryption == false`). For large documents this is a needless memory/performance regression compared to the previous behavior where `fpassthru()` streamed the file without buffering it all in memory.

**Severity: Medium** — performance/reliability concern for large files, possible memory-exhaustion risk.

---

### 3. **No error handling for `fopen`/`filesize`**
**Location:** `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));`

If `$url` doesn't exist or isn't readable, `fopen` returns `false` and `filesize()` returns `false`, causing `fread(false, false)` to emit warnings and likely return `false`/empty. There is no validation before this operation making reliability worse than before (where this was only reached in the narrower encryption branch, and even there w/o checks, but now this path is hit on every original-file request).

**Severity: Medium**

---

### 4. **Resource leak: `$f` never closed**
**Location:** same block.

The file handle opened with `fopen()` is never explicitly closed (`fclose($f)`), including in the new early-`return $filetext;` path. This was already a minor issue before, but the new early-return paths make the leak more likely to occur across many calls (e.g., batch retrieval with `$disable_exit = true`).

**Severity: Low**

---

### 5. **Inconsistent `disable_exit` behavior in the "converted file" branch**
**Location:**
```php
if($disable_exit == true) {
    return ;
}
header("Pragma: public");
```
In this branch (handling converted/mime-type files), when `$disable_exit` is true the function simply returns `null` instead of returning the file content, unlike the other two branches (CouchDB retrieval and original-file retrieval) which return the actual decoded/file content. Any caller relying on `retrieve_action(..., true)` to always get back the document body will silently get `null` for converted files, which looks like an incomplete implementation and could cause confusing downstream bugs.

**Severity: Medium** — functional inconsistency/incomplete feature.

---

### 6. **Style / maintainability: mixed indentation**
**Location:** new lines use spaces for indentation while the rest of the method uses tabs (e.g. the `if($disable_exit == true) { ... }` blocks).

This is inconsistent with the surrounding code style and will show up as noisy diffs/alignment issues in future PRs.

**Severity: Low (style/maintainability)**

---

### Summary
The intent of adding a `$disable_exit` flag to let `retrieve_action()` return content instead of streaming it directly is reasonable, but the implementation:
- **breaks the default (non-encrypted) file-download path** due to the file pointer being exhausted by an unconditional `fread()` (critical correctness bug),
- introduces unnecessary memory overhead for all original-file requests,
- lacks error handling around file operations,
- is inconsistent in the converted-file branch (returns `null` instead of content),
- leaks file handles,
- and has minor style inconsistencies.

The file-pointer/`fread` issue (#1) should block merging until fixed, e.g. by only reading the whole file when actually needed (encryption or `disable_exit`), and using `rewind($f)` or a separate read when falling through to `fpassthru()`.