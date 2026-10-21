## Review summary

**The diff itself is a security improvement, and I found no new vulnerabilities in it.** Removing `LIBXML_XINCLUDE` stops libxml from resolving `<xi:include href="...">` automatically. That feature lets attacker-controlled XML read local files (`file:///etc/passwd`, application config, credentials) or make outbound requests (`http://169.254.169.254/...`). It is an XXE-style file disclosure and SSRF vector. The change should be merged, but the points below cover the surrounding code it touches or relies on.

### Issues in the touched code

**1. `LIBXML_PARSEHUGE` still enabled** (`XmlExtended.php`, both `open()` and `XML()` calls)
- **OWASP:** A05 Security Misconfiguration (also A04 Insecure Design)
- **Problem:** This flag disables libxml2's limits on depth, entity expansion and text node size. A CDA/XML document from an untrusted source (such as an uploaded patient record) can exhaust memory or CPU. Examples are a billion-laughs payload or a very deeply nested document.
- **Severity:** Medium (denial of service)
- **Fix:** Drop the flag unless large documents are a documented requirement. If they are, enforce an upload size limit and a nesting limit before parsing.

**2. No `LIBXML_NONET` and no explicit entity and DTD hardening** (same lines)
- **OWASP:** A05 Security Misconfiguration, A10 SSRF, A03 Injection (XXE)
- **Problem:** Removing XInclude closes one vector, but external DTDs and entities are still not blocked by flags. The code is only safe if nothing enables entity substitution (`XMLReader::SUBST_ENTITIES`, `LIBXML_NOENT`, `LIBXML_DTDLOAD`) elsewhere in the class or its parent, and if the libxml version defaults are safe. This is fragile.
- **Severity:** Medium. It becomes High if substitution is enabled anywhere in the class hierarchy.
- **Fix:** Add `LIBXML_NONET`. Do not enable `LIBXML_NOENT` or `LIBXML_DTDLOAD`. Reject documents that contain a `<!DOCTYPE>`, for example by checking for `XMLReader::DOC_TYPE` nodes and aborting.

**3. `$filename` passed straight to `XMLReader::open()`** (first hunk)
- **OWASP:** A01 Broken Access Control (path traversal), A10 SSRF
- **Problem:** `open()` accepts URLs and PHP stream wrappers such as `http://`, `php://` and `phar://`. The visible code only checks that the file is readable. If any caller lets a user influence `$filename`, this becomes arbitrary file read or SSRF.
- **Severity:** Medium (depends on callers)
- **Fix:** Allow-list the directory with `realpath()`. Reject any path containing a scheme.

**4. `$this->directory = dirname($filename)`, an include-resolution leftover**
- **OWASP:** A01 Broken Access Control (path traversal)
- **Problem:** The parent Laminas-style `Xml` reader can process `include` elements manually, resolving `href` relative to `$directory`. If that logic is still active, removing the libxml flag does not remove the include behavior. A document containing `../../` or an absolute path or URL could still pull in arbitrary files. I could not see that code in this diff, so please verify it.
- **Severity:** Medium to High if present
- **Fix:** Remove the manual include handling, or restrict it to `realpath()` results inside an allow-listed base directory.

**5. Error handling and logging** (the `set_error_handler` closure)
- **OWASP:** A09 Logging and Monitoring Failures
- **Problem:** Parse errors are converted to exceptions or silenced. Confirm that the handler is always restored (use `try/finally`) and that rejected or malformed documents are logged. Repeated malformed or malicious XML should be visible to monitoring.
- **Severity:** Low

### Recommendation
Approve the change. Before or soon after merging, add `LIBXML_NONET`, remove or justify `LIBXML_PARSEHUGE`, block DOCTYPE declarations, and audit the remaining include and `$directory` handling in the parent class. Add a test that confirms an `xi:include` pointing at a local file is not expanded.