## Review Comments

**Location:** `src/Services/Cda/XmlExtended.php`, both `open()` (fromFile) and `XML()` (fromString) calls — removal of `LIBXML_XINCLUDE`

### 1. Functional regression risk (Major)
`LIBXML_XINCLUDE` instructs libxml to resolve `<xi:include>` elements during parsing. CDA documents frequently use XInclude to assemble multi-part content (e.g., pulling in external sections, attachments, or shared templates). Removing this flag means any such documents will no longer have their includes resolved — the raw `<xi:include>` elements will be left in the tree instead of being replaced by their referenced content. This will silently produce incomplete/incorrect parsed output rather than throwing an error, which is a particularly dangerous failure mode (data loss without obvious symptoms).

Before merging, it should be verified that no CDA documents processed by this reader actually depend on XInclude for correct behavior. If any do, this change breaks them.

### 2. Likely security motivation is reasonable, but incomplete (Medium)
Disabling XInclude is a sensible security hardening step: XInclude can be abused similarly to XXE to read arbitrary local files (`<xi:include href="file:///etc/passwd" parse="text"/>`) or to fetch remote resources (SSRF), especially if the input XML is not fully trusted (e.g., CDA files uploaded by external parties). So the removal does close one attack vector.

However:
- The diff does not add `LIBXML_NONET`, so even without XInclude, if DTD/entity processing is enabled elsewhere (e.g., via `setParserProperty`), network-based resource fetching is still possible.
- There is no explicit call to disable external entity loading (`libxml_disable_entity_loader()` on older PHP, or ensuring `LIBXML_NOENT` is never set and `XMLReader::LOADDTD`/`XMLReader::VALIDATE` remain off). This isn't new in this diff, but since the PR is clearly addressing XML-processing security here, it's worth calling out that the fix is partial — an attacker-controlled CDA file could still trigger other XXE-class issues if DTDs are processed upstream or downstream of this reader.

### 3. No accompanying tests or comment explaining the change (Minor/Maintainability)
There’s no test added/updated to confirm that (a) XInclude-based attacks are now blocked, or (b) legitimate CDA parsing still works without it. A one-line flag removal with no comment explaining *why* (security vs. unintended side effect) will confuse future maintainers who may "helpfully" re-add the flag. A code comment referencing the security rationale (and a regression/security test) would significantly improve maintainability and prevent silent reintroduction of the vulnerability.

### 4. Consistency check needed elsewhere in codebase (Minor)
If other readers/parsers in the codebase (e.g., a plain `Xml` reader class, or other CDA/XML ingestion points) also set `LIBXML_XINCLUDE`, they should be audited and fixed consistently, otherwise this fix only closes the hole in one of several entry points.

---

**Summary:** The intent (removing XInclude processing, presumably for security reasons) is reasonable, but it is a behavior change that can silently corrupt output for any input relying on `xi:include`, it doesn't fully address the broader XXE/XInclude-class risk, and it lacks tests/documentation justifying the change. I'd ask the author to confirm no legitimate use of XInclude exists in current CDA inputs, and to add a regression test plus a brief comment noting the security rationale.