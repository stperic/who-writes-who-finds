# Review: remove `LIBXML_XINCLUDE` from `XmlExtended` CDA parsing

## Summary

Removing `LIBXML_XINCLUDE` is a good security fix. XInclude processing on untrusted CDA documents lets an attacker pull local files into the parsed output (for example `<xi:include href="/etc/passwd" parse="text"/>`), or reach remote URLs (SSRF). I support merging the change. The remaining issues are below.

## Issues

### 1. `LIBXML_PARSEHUGE` still enabled on untrusted input — Medium/High (security, pre-existing)

**Location:** `XmlExtended.php` lines 39 and 73.

**Problem:**
- `LIBXML_PARSEHUGE` turns off libxml's built-in safety limits. These include maximum nesting depth, maximum text node size, and entity expansion limits.
- CDA documents are typically uploaded or received from outside parties.
- With these limits off, a crafted document can exhaust memory or CPU. Examples are very deep nesting, giant text nodes, or entity amplification ("billion laughs") if entities get expanded anywhere downstream.
- This is a denial-of-service vector on any import endpoint.

**Recommendation:**
- Drop `LIBXML_PARSEHUGE` unless real CDA files actually exceed the default limits.
- If the flag is needed, enforce an upload or document size cap before parsing.
- Consider `LIBXML_NONET` to block network access during parsing.
- Make sure `LIBXML_NOENT` and `LIBXML_DTDLOAD` are never added.

### 2. Possible functional regression for documents relying on XInclude — Medium (correctness)

**Location:** both parse paths.

**Problem:**
- Any CDA or CCDA files, or internal templates, that legitimately used `xi:include` will now parse without that content.
- This happens silently, with no error.
- `$this->directory = dirname($filename)` is still set. It may have existed to resolve relative includes, so it could now be dead code or misleading.

**Recommendation:**
- Confirm that no supported input uses XInclude.
- If something does, resolve includes explicitly against a whitelisted base directory instead of letting libxml do it.
- Remove or document `$this->directory` if it is no longer used for this purpose.

### 3. Return value of `XMLReader::open()` / `XMLReader::XML()` not checked — Low (reliability, pre-existing)

**Location:** lines 39 and 73.

**Problem:**
- Both methods return `false` on failure.
- The code goes straight on to use `$this->reader`, so failures show up later as confusing errors rather than a clear parse failure.

**Recommendation:** Check the result and throw a descriptive exception.

### 4. No test coverage for the security fix — Low (maintainability)

**Problem:** Nothing prevents a future change from re-adding `LIBXML_XINCLUDE`.

**Recommendation:** Add a regression test. Parse a document containing an `xi:include` of a local file and assert that the file's contents do not appear in the output.