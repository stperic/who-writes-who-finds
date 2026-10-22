## Review Comments

### 1. Behavior change: whole file now always loaded into memory (regression)
**Location:** `C_Document.class.php`, `retrieve_action()`, "normal case when serving the file referenced in database" block

```php
$f = fopen($url,"r");
$filetext = fread( $f, filesize($url) );
if($disable_exit == true) {
    return $filetext;
}
...
if ( $doEncryption ) {
    $ciphertext = $this->encrypt( $filetext, $passphrase );
```

Previously, `fread($f, filesize($url))` only ran inside the `$doEncryption` branch. After this change it runs unconditionally, even for the normal (non-encrypted, non-`disable_exit`) download path. That path presumably later streams the file (e.g. via `fpassthru`/`readfile`), so loading the entire file into a PHP string first is unnecessary and can cause high memory usage or failures for large documents.

**Severity:** Medium (performance/reliability regression for large files)

---

### 2. No error handling around `fopen`/`filesize`/`fread`
**Location:** Same block as above

`fopen($url, "r")` can return `false` if the file is missing or unreadable, and `filesize($url)` returns `false` on failure. Neither is checked. `fread($f, false)` will silently behave unexpectedly rather than failing loudly, making debugging “file not found” issues harder. There’s also no `fclose($f)` after reading, so the handle is leaked on every call.

**Severity:** Low–Medium (reliability/maintainability)

---

### 3. Inconsistent/incomplete behavior for `disable_exit` in the converted-file branch
**Location:** Third hunk, inside the `else` branch handling the converted file path

```php
if($disable_exit == true) {
    return ;
}
```

Unlike the other two code paths (CouchDB retrieval and “original file”), which return the actual file content when `$disable_exit` is true, this branch just returns `null` without ever reading/returning the converted file’s content. Any caller that passes `disable_exit=true` expecting to get file bytes back for a converted document will silently receive nothing instead, which looks like a correctness bug rather than an intentional "no-op" for this path.

**Severity:** Medium–High (correctness; silent failure for a subset of callers)

---

### 4. Mixed tabs/spaces in new code
**Location:** All three added `if($disable_exit == true) { ... }` blocks

The surrounding file is indented with tabs; the newly added blocks use spaces, producing visibly misaligned code and inconsistent style. This is a minor nit but worth fixing for maintainability/diff readability.

**Severity:** Low (style/maintainability)

---

### 5. No documentation of new parameter / behavior contract
**Location:** Function signature change

```php
function retrieve_action($patient_id="",$document_id,$as_file=true,$original_file=true,$disable_exit=false) {
```

There’s no comment explaining what `disable_exit` does, what callers should expect it to return (raw bytes vs. base64, when it returns `null`, etc.), especially given the inconsistency noted in #3. Since this is a public controller action that other code will likely call directly to reuse file-retrieval logic, the contract should be documented.

**Severity:** Low (maintainability)

---

### Summary
The most important issues are **#1** (unconditional full-file read regressing a previously conditional/streamed path) and **#3** (the converted-file branch doesn’t actually honor `disable_exit` by returning content, unlike the other two branches). These should be addressed before merge; the others are minor cleanups.