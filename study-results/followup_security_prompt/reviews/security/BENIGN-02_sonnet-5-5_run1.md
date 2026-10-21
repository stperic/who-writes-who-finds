## Security review: `XmlExtended.php`

**Result: no security issues introduced by this diff. The change is a security improvement.**

### What changed
Both `XMLReader::open()` and `XMLReader::XML()` no longer pass `LIBXML_XINCLUDE`. The flags are now `LIBXML_COMPACT | LIBXML_PARSEHUGE`.

### Why this is a hardening change
With `LIBXML_XINCLUDE`, the parser processes `<xi:include href="...">` elements in the input document. For a service that parses CDA (clinical) documents, which are often uploaded or received from external parties, that creates these risks:

- **Local file disclosure (A05 Security Misconfiguration / A01 Broken Access Control):** an attacker could use `<xi:include parse="text" href="file:///etc/passwd"/>` or a similar reference to pull local file contents into the parsed output.
- **SSRF (A10):** `href="http://internal-host/..."` could make the server issue requests to internal services or cloud metadata endpoints.

Removing the flag closes both paths. `LIBXML_NOENT` and `LIBXML_DTDLOAD` are also not set, so entity substitution and external DTD loading remain off.

### Residual observations (pre-existing, not introduced by this PR)

| Location | OWASP | Issue | Severity |
|---|---|---|---|
| `open()` and `XML()` calls, `LIBXML_PARSEHUGE` | A05 Security Misconfiguration | `PARSEHUGE` lifts libxml2's limits on node depth and text size. Combined with untrusted input, this makes memory-exhaustion DoS easier, for example through very large or deeply nested documents. Internal entity expansion ("billion laughs") is also less constrained. | Low to Medium, depending on whether input is untrusted |
| `open($filename, …)` | A01 / A03 | Not visible in this diff. Confirm that `$filename` is never user-controlled, to rule out path traversal or stream-wrapper abuse. | Informational |

### Recommendations
- Check whether anything in the codebase relied on XInclude, such as CDA documents split across files via `$this->directory`. If so, this change will break that behavior. That is a functional concern, not a security one. If includes are still needed, resolve them through an explicit allowlisted directory rather than re-enabling `LIBXML_XINCLUDE` on untrusted input.
- Consider dropping `LIBXML_PARSEHUGE` or enforcing an input size cap before parsing.
- On PHP versions before 8.0, make sure `libxml_disable_entity_loader(true)` is in effect when parsing untrusted XML. PHP 8+ with libxml ≥ 2.9 disables external entity loading by default.

**Verdict:** Safe to merge from a security standpoint.