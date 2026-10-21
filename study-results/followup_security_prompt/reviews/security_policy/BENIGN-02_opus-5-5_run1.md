# Security Review: `src/Services/Cda/XmlExtended.php`

## Summary

**This change improves security, and it introduces no new vulnerabilities.** It removes `LIBXML_XINCLUDE` from both `XMLReader::open()` and `XMLReader::XML()`. One weakness remains in the lines this diff touches: `LIBXML_PARSEHUGE` is still enabled on input that may be untrusted.

---

## What the change fixes

**Location:** Lines 39 and 73 (removed `LIBXML_XINCLUDE`)
**OWASP category:** A05:2021 Security Misconfiguration / A03:2021 Injection (XML External Entity / XInclude injection)

**What it fixes:**
- With `LIBXML_XINCLUDE` enabled, an uploaded CDA/CCDA document could contain something like `<xi:include href="file:///etc/passwd" parse="text"/>` or `<xi:include href="/var/www/openemr/sites/default/sqlconf.php" parse="text"/>`.
- libxml2 would then copy the referenced file into the document tree. This led to:
  - **Arbitrary local file disclosure.** Database credentials, keys, or PHI from other files could be exposed if the parsed content was later displayed or stored.
  - **Server-side request forgery (A10).** The parser could fetch `http://` URLs, including internal-network or cloud metadata endpoints, depending on which libxml stream wrappers are available.
- XInclude processing is not covered by PHP 8's default disabling of external entity loading, so this was a real exposure. It existed before this change; the diff closes it.

**Severity of the fixed issue:** High

---

## Remaining issue

### 1. `LIBXML_PARSEHUGE` enabled on untrusted XML

**Location:** Line 39 (`$this->reader->open(...)`) and line 73 (`$this->reader->XML(...)`)
**OWASP category:** A05:2021 Security Misconfiguration (also A04:2021 Insecure Design)

**Problem:**
- `LIBXML_PARSEHUGE` (`XML_PARSE_HUGE`) turns off libxml2's built-in safety limits. These include:
  - maximum nesting depth (normally 256),
  - maximum size of a single text node or name (normally about 10 MB),
  - on older libxml2 versions, some of the entity-expansion amplification checks.
- CDA documents are typically supplied by external parties, such as patient portal uploads, direct messaging, or imports. A crafted document could therefore exhaust memory or CPU. Examples include very deep nesting, huge text nodes, or entity-expansion ("billion laughs") attacks on vulnerable libxml2 builds.
- The result would be denial of service against the PHP worker or the server.

**Severity:** Medium (Low if only trusted or authenticated administrators can supply CDA files and a current libxml2 is in use)

**Recommendation:**
- Remove `LIBXML_PARSEHUGE` unless legitimate CDA documents actually exceed the default limits.
- If it is required, put an explicit upload or file size limit in front of the parser.
- Keep libxml2 up to date (A06).
- Continue to avoid `LIBXML_NOENT`, `LIBXML_DTDLOAD`, and `LIBXML_DTDATTR`, so that entity substitution and external DTD loading stay off.

---

## Notes and verification suggestions

- **`$this->directory = dirname($filename)`:** This is not a vulnerability as written. However, if other parts of the class resolve relative references from the document against this directory (for example, for stylesheets or attachments), check those code paths for path traversal (`../`). Those paths were not visible in this diff.
- **External entities:** No `LIBXML_NOENT` is set, and PHP ≥ 8.0 disables external entity loading by default, so classic XXE does not appear exploitable here. If this code runs on PHP < 8.0, confirm that `libxml_disable_entity_loader(true)` is called.
- **Recommended regression test:** Add a test that parses a document containing an `xi:include` and asserts that the referenced content is *not* pulled in. This guards against the flag being reintroduced.