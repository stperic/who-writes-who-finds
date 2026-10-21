# Pull Request Review: XmlExtended.php

## Issue Found

**Location:** Lines 39 and 73

**Problem:** Removal of `LIBXML_XINCLUDE` flag

The diff removes the `LIBXML_XINCLUDE` flag from both `XMLReader::open()` and `XMLReader::XML()` calls. This flag enables processing of XInclude elements in XML documents.

**Severity:** HIGH

**Details:**
- If the XML documents being processed contain XInclude directives (e.g., `<xi:include href="..." />`), they will no longer be expanded after this change
- This could break existing functionality if:
  - The CDA documents rely on XInclude for modular XML composition
  - External XML fragments are expected to be included and processed
- The removal appears intentional but lacks context—no commit message is visible explaining the rationale

**Recommendation:**
1. Clarify why `LIBXML_XINCLUDE` was removed. Is this intentional to prevent XInclude processing?
2. If intentional, add a code comment explaining the security or functional rationale
3. Verify that no existing CDA documents in production rely on XInclude expansion
4. Add or update tests to confirm the expected behavior with/without XInclude processing

---

## Additional Security Note

**Existing concern (pre-existing, not introduced by this change):**

The code uses `XMLReader::open()` with user-supplied `$filename` without apparent validation. Combined with `LIBXML_PARSEHUGE`, this could be exploited for XXE (XML External Entity) attacks or billion laughs DoS if the file path is user-controlled. Ensure proper input validation exists upstream.