## Review: removing `LIBXML_XINCLUDE` from the CDA XML readers

**Summary:** The diff drops `LIBXML_XINCLUDE` from both `XMLReader::open()` (file path) and `XMLReader::XML()` (string path). The change is small, but the PR gives no rationale, and I'd want a few things confirmed before merging.

### Issues

**1. Missing rationale and tests (Maintainability, Medium)**
- Location: the whole diff.
- The PR does not say why XInclude is being disabled. It could be a security hardening, a bug fix, or a cleanup. The reviewer and future maintainers need that context, ideally in the PR description or a commit message.
- No test shows the intended behavior. Add tests for both paths: a document with an `xi:include` (should it be ignored or resolved?) and a document with no includes (should parse as before).

**2. Possible behavior change for real documents (Correctness, Medium)**
- Location: both changed lines.
- If any CDA documents in use rely on `xi:include` to pull in sections, those sections will now be silently absent. Nothing in the diff signals an error or warning, so the parsed output would just be incomplete.
- The `$this->directory = dirname($filename)` assignment suggests relative includes were expected to resolve against the document's directory. Confirm whether that is still needed; if XInclude is gone, that assignment may now be dead code.
- Suggested check: search the test fixtures and sample CDA documents for `xi:include`, and decide whether the removal should log or reject such documents instead of ignoring them silently.

**3. Verify the flag had any effect (Correctness, Low)**
- Location: both changed lines.
- With PHP's `XMLReader`, passing `LIBXML_XINCLUDE` to `open()` or `XML()` does not by itself perform XInclude processing. Processing generally requires calling `$reader->setParserProperty()` or `xinclude()` explicitly, or doing the expansion in a DOM step. If the flag was already inert, this change is a no-op and the real XInclude processing lives elsewhere. In that case the PR is either incomplete (the real code path is still active) or the description is misleading. Please confirm which.

**4. Security note (Positive, but verify)**
- XInclude can read local files and pull remote resources, which is an XXE-style risk when parsing untrusted CDA documents. Removing it is a reasonable hardening, provided no other code path still calls `xinclude()` (for example on a `DOMDocument` elsewhere in the class or in the `Xml` parent).
- Also confirm that external entity loading is disabled on the same paths. Removing XInclude does not cover entity expansion.

### Recommendation
Approve only after the PR explains the motivation, a test covers an `xi:include` document, and a search confirms no other XInclude processing remains. If the change is a security fix, say so in the description and consider a release note, since it is a user-visible change to parsed output.