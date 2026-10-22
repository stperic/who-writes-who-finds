## Review: `retrieve_action` gains a `$disable_exit` flag

The diff adds a `$disable_exit` parameter that returns file content instead of sending it. I would not merge it as written. The main problems are a silent encryption bypass, an unvalidated flag on a request-dispatched action, and a memory regression. Each is detailed below.

### 1. Encryption is skipped when `$disable_exit` is true (High)
**Location:** `original_file` branch, the `if($disable_exit == true) { return $filetext; }` block.

The early return happens before the `if ( $doEncryption )` check. A caller that passes `$disable_exit = true` together with an encryption request gets back the plaintext, with no error and no indication that encryption was skipped. The CouchDB branch has the same pattern: `return base64_decode($content);` runs before any encryption handling that follows the header block. For a document-export feature, returning unencrypted content when the user asked for encryption is a confidentiality failure.

**Fix:** Apply the encryption step to the returned content, or refuse the combination of `disable_exit` and `doEncryption`.

### 2. The flag is an unvalidated input on a web-reachable action (Medium)
**Location:** the signature `retrieve_action(..., $disable_exit=false)`.

Controller actions in this codebase are typically dispatched from request parameters. If that holds here, any client can supply `disable_exit` and change the function's control flow. The worst case is that the action returns without sending headers or exiting, so the surrounding framework continues and may emit extra output or skip cleanup. Internal callers should set this flag, not HTTP clients.

**Fix:** Keep the flag out of the request-dispatched signature, for example by moving the file-reading logic into a separate helper that both the action and internal callers use. Otherwise, at minimum, confirm the dispatcher cannot pass it.

### 3. Whole-file read on every request (Medium, regression)
**Location:** `$f = fopen($url,"r"); $filetext = fread($f, filesize($url));` now runs before the `doEncryption` check.

Before this change, the unencrypted path streamed the file to the client. Now every request reads the entire file into memory, including the common non-encrypted download. Large documents could exhaust `memory_limit`.

**Fix:** Read into memory only when `$disable_exit` or `$doEncryption` requires it. Otherwise keep the original streaming path.

### 4. No error handling on `fopen` / `filesize` (Low)
**Location:** the same block.

If `$url` is missing or unreadable, `fopen` returns `false` and `fread`/`filesize` emit warnings. The code then proceeds to send headers and return an empty or invalid body. The original code had the same gap, but the read now happens earlier and is used for more paths.

**Fix:** Check the `fopen` result and fail cleanly, for example by logging and returning an error.

### 5. Resource leak and naming (Low)
- In the `disable_exit` path, `$f` is never closed. PHP will release it at request end, but the handle should be closed explicitly.
- The name `disable_exit` does not describe the behavior. The function returns content instead of sending it. A name such as `return_content` would be clearer and would make the mixed control flow easier to follow.
- The new lines use spaces where the surrounding code uses tabs, which makes the diff inconsistent.

### Summary
| # | Location | Severity | Issue |
|---|----------|----------|-------|
| 1 | original_file / CouchDB early return | High | Encryption silently skipped when `$disable_exit` is set |
| 2 | Function signature | Medium | Control-flow flag may be attacker-controllable via request |
| 3 | fopen/fread placement | Medium | Entire file loaded into memory for all downloads |
| 4 | fopen/filesize | Low | No error check on file open |
| 5 | Return path, naming, style | Low | Handle not closed; misleading name; mixed indentation |

The change needs a redesign before merge, mainly to fix the encryption bypass (issue 1) and separate internal content retrieval from the HTTP download path (issue 2).