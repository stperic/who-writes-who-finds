## Review of the `XmlExtended` XInclude change

**Overall:** The change removes `LIBXML_XINCLUDE` from both `XMLReader::open()` and `XMLReader::XML()`. Dropping XInclude processing is a reasonable hardening step for a parser that handles untrusted CDA documents, so I'd support the direction. I have a few concerns about how it is done.

### 1. Behavior change with no description or test (Medium)
**Location:** `XmlExtended.php`, both `open()` and `XML()` calls.

The PR doesn't say whether the change is intentional hardening or a fix for a specific problem. If any CDA documents processed by this reader rely on `xi:include` to pull in sections, those sections will now be silently skipped, and the output will change without any error. The PR should:
- State the reason (for example, "prevent XInclude-based file disclosure from untrusted CDA") and whether it is a security fix.
- Confirm that no fixtures or production inputs depend on XInclude.
- Add a test showing that an `xi:include` of a local file (such as `/etc/passwd` or a file next to the document) is no longer resolved.

### 2. `$this->directory` is still set (Low)
**Location:** `XmlExtended.php`, the `open()` path.

`$this->directory = dirname($filename);` is retained. If that value is used to resolve relative references from the document, it may still permit reading files relative to the source document. That is worth checking. If it is only used for other resources, nothing changes here. If XInclude was the only consumer, the directory handling may now be dead code and should be reviewed.

### 3. Check for other XInclude paths (Low, needs verification)
Removing the flag from the reader does not disable XInclude if the code elsewhere calls `->xinclude()` on the reader or `xinclude()` on a `DOMDocument` built from expanded nodes. Please grep for `xinclude(` and `XINCLUDE` across `src/` to confirm that no other path re-enables it.

### 4. Pre-existing: `LIBXML_PARSEHUGE` (Low, not introduced by this change)
**Location:** both calls, unchanged.

`LIBXML_PARSEHUGE` relaxes libxml2's depth and size limits. Combined with untrusted input, this increases resource-exhaustion risk. It is not needed for the XInclude change. Consider removing it unless large documents are known to require it, and add a comment explaining why if it stays.

### Summary

| # | Location | Issue | Severity |
|---|---|---|---|
| 1 | `open()` / `XML()` | Undocumented behavior change; no tests or rationale | Medium |
| 2 | `open()`, `$this->directory` | Directory retained; may still enable relative file access | Low |
| 3 | Whole `src/` | Other code may re-enable XInclude; needs verification | Low |
| 4 | Both calls | `LIBXML_PARSEHUGE` weakens resource limits (pre-existing) | Low |

The security direction is correct, but I'd ask for the rationale, a regression test, and a check of the points above before merging.