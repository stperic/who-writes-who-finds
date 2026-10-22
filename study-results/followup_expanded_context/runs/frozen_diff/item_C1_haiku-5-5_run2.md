## Review of `retrieve_action` changes: `$disable_exit` parameter

### 1. Early return bypasses encryption in the file branch (High)
**Location:** `C_Document.class.php`, original-file branch, the `if($disable_exit == true) { return $filetext; }` block.

The new return runs before the `if ( $doEncryption )` block. When the user requested an encrypted download (`$_POST['encrypted']` set, so `$doEncryption` is true), a caller using `disable_exit` gets the plaintext file contents back and the encryption step is skipped. Any caller that relies on this function to honour the encryption request will silently return unencrypted data.

Fix: apply the encryption step before the early return, or refuse `disable_exit` when `$doEncryption` is true.

### 2. Same concern in the CouchDB branch (High, needs verification)
**Location:** the CouchDB block, `if($disable_exit == true) { return base64_decode($content); }`.

The early return is placed before the header and output logic. If the CouchDB path also applies passphrase encryption when `$encrypted` is set (which the surrounding variables suggest), this branch has the same bypass as issue 1. Confirm the encryption step runs before the return.

### 3. Dispatch exposure of a control parameter (Medium, needs verification)
`disable_exit` is a positional argument on an action method. If the controller dispatcher forwards request parameters positionally or via `call_user_func_array`, a remote user could set it and change the function's behaviour (returning content instead of streaming it). Check how actions are invoked. If they can be reached from request input, the parameter should be set only by internal callers, or the behaviour should be moved to a separate internal method.

### 4. File handle and memory handling in the original-file branch (Medium)
- `fopen($url,"r")` is now called before any check. If the file is missing or unreadable, `fopen` returns false and `fread`/`filesize` emit warnings with no error handling.
- The handle `$f` is never closed on the new `return` path.
- The whole file is now read into memory on every download, including the non-encrypted path that previously streamed it. This is a regression for large documents.

Fix: check the `fopen` result, `fclose` before returning, and read the file into memory only when it is needed.

### 5. Inconsistent return values (Low/Medium)
- The CouchDB and original-file paths return data (a string).
- The converted-file path does `return ;` (null).
- Other paths still `die()` or exit.

A caller cannot tell a successful empty result from a failure. Return a consistent type, or document the contract (for example, `false` on error).

### 6. Behaviour change relative to the name (Low)
The parameter is named `disable_exit`, but it changes the return type and skips encryption rather than only skipping `exit`/`die`. The name and the docblock should describe the actual contract. There is also no docblock for the new parameter.

### 7. Style (Low)
Mixed tabs and spaces in the new lines, and `== true` comparisons where `if ($disable_exit)` would do.

### Summary
The main problem is that the `disable_exit` short-circuits skip the encryption step, which can return plaintext when encryption was requested (issues 1 and 2). I would not merge until that is fixed. Issue 3 should be verified, and issues 4 and 5 should be addressed in the same change.