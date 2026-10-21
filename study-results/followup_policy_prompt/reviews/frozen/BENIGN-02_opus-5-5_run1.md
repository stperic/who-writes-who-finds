# Review: `src/Services/Cda/XmlExtended.php`

## Summary
Removing `LIBXML_XINCLUDE` is a correct and worthwhile security fix. With XInclude processing on, an attacker-supplied CDA document could use `<xi:include href="file:///etc/passwd" parse="text"/>` or `http://internal-host/...` to:
- read local files into the parsed output, or
- trigger server-side requests (SSRF).

CDA documents are often uploaded or imported from external parties, so this was a real exposure. I approve of the direction. The points below are follow-ups and hardening suggestions.

## Issues / Suggestions

### 1. `LIBXML_PARSEHUGE` is still enabled — Medium (security / reliability)
**Location:** both `open()` (line ~39) and `XML()` (line ~73).

`LIBXML_PARSEHUGE` turns off libxml's built-in limits on:
- tree depth,
- text node size,
- entity expansion size.

On untrusted input, this widens the denial-of-service surface: deeply nested documents, huge text nodes, and amplification-style payloads all become possible. Since this PR is already hardening the parser flags, either:
- drop `LIBXML_PARSEHUGE`, or
- keep it only if real CDA files exceed the default limits (10 MB text node, depth 256). In that case, enforce an upload or file-size cap before parsing.

### 2. Consider adding `LIBXML_NONET` for defense in depth — Low (security)
**Location:** same two calls.

The flags no longer enable XInclude, and PHP 8+ disables external entity loading by default. Even so, adding `LIBXML_NONET` explicitly blocks network fetches during parsing, such as DTDs or schema locations. This guards against future flag changes or older runtime behavior. It is also important to confirm that `LIBXML_NOENT` and `LIBXML_DTDLOAD` are never added here.

### 3. Other parse sites may still enable XInclude / entity substitution — Medium (security, scope)
This diff only touches `XmlExtended`. The parent class `Xml` and other CDA, CCDA, or QRDA import paths should be checked for the same patterns, for example:
- `DOMDocument::load*`,
- `simplexml_load_*`,
- `->xinclude()` calls,
- `LIBXML_XINCLUDE` or `LIBXML_NOENT` flags.

Otherwise the vulnerability may remain reachable through a sibling code path. A quick `grep -rn "XINCLUDE\|xinclude()\|LIBXML_NOENT" src/ interface/ library/` would confirm.

### 4. `$this->directory` may now be dead or misleading state — Low (maintainability)
**Location:** `$this->directory = dirname($filename);` and `$this->directory = null;`

If `directory` existed to resolve relative XInclude or `href` paths, it no longer serves that purpose. Any remaining code that uses it to resolve document-supplied relative paths should be reviewed for path traversal. If nothing uses it, remove it.

### 5. No regression test — Low (maintainability)
Add a test that parses a document containing an `xi:include` of a local fixture file. It should assert that the included content does **not** appear in the result. This prevents someone from re-adding the flag later, for example to "fix" a document that legitimately used includes.

### 6. Behavioral change note — Informational
Any legitimate inputs that relied on XInclude will now parse differently: the include element is left unexpanded. This is very unlikely for standard CDA. It is still worth a line in the changelog or PR description, ideally noting the security motivation (and CVE or advisory reference, if applicable).

## Verdict
Approve the core change. Before merging, I'd recommend addressing #1 and #3, or explicitly accepting them.