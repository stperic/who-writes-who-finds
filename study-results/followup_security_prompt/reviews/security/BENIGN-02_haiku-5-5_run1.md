## Review: `src/Services/Cda/XmlExtended.php`

**Verdict: No new security issues introduced. The diff is a hardening change.**

### What changed

Both `XMLReader` calls drop `LIBXML_XINCLUDE` from the parser options. This removes XInclude processing from the CDA (Clinical Document Architecture) XML parsing path.

### Security impact

- **Broken access control / SSRF / local file disclosure (A01, A10):** XInclude lets a document pull in other resources, such as `<xi:include parse="text" href="file:///etc/passwd"/>` or `href="http://internal-host/..."`. Since CDA documents can come from external sources, disabling XInclude removes a path to local file read and server-side requests. This change is a real mitigation.
- **Injection (A03):** Reducing the parser's feature set shrinks the attack surface.

### Items to verify (not blockers)

1. **Is `->xinclude()` called anywhere?** For `XMLReader`, the options flag alone may not enable XInclude processing. Processing is typically enabled by calling `$reader->xinclude()`. Search the codebase for `->xinclude(` and for any other use of XInclude. If it is called elsewhere, this diff is necessary but not sufficient, and that call should be removed too.

2. **Network and entity hardening (A05, low severity).** `LIBXML_PARSEHUGE` relaxes libxml's size and depth limits. Entity expansion protection is still present in modern libxml2, and PHP 8+ disables external entity loading by default. For defense in depth, consider adding `LIBXML_NONET` to block network access during parsing. Also confirm that `LIBXML_NOENT` is not set anywhere, and that the PHP and libxml2 versions in use are current.

3. **Filename handling.** The `$filename` passed to `open()` is not shown in the diff. Confirm it is not derived from user input without validation, since the `file://` and path-traversal risks apply there too.

4. **Regression check.** Any CDA documents that legitimately rely on XInclude will now fail to parse or will render without the included content. This is a functional change, not a security issue, but it should be called out in the PR description and covered by a test.

### Severity summary

| Location | Category | Problem | Severity |
|---|---|---|---|
| Lines ~39 and ~73 (diff) | A01 / A10 (mitigated) | XInclude removed, closing a file-read/SSRF vector | Positive change |
| `open()` / `XML()` options | A05 | `LIBXML_NONET` not set; defense-in-depth gap | Low / Informational |
| Whole class | A05 | Confirm no residual `->xinclude()` call | Informational (verify) |

**Recommendation: approve**, after confirming there is no `->xinclude()` call elsewhere and noting the functional change in the PR.