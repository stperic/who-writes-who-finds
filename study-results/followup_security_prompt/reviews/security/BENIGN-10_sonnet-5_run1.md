This diff only changes client-side JavaScript logic (fixing a type comparison bug: comparing a string value from `.value` against the number `1`, now properly parsed with `parseInt`).

**Security review:**

No security vulnerabilities were introduced or found in this diff relative to the OWASP Top 10 (2021).

Observations:
- **Nature of change**: Purely a bug fix in client-side arithmetic/display logic for payment calculation UI (converting a DOM string value to an integer before comparison). It does not touch authentication, authorization, data persistence, output encoding, or external requests.
- **Injection/XSS**: No new user input is rendered or concatenated into HTML/SQL; the values involved (`HiddenIns`, `Allowed`, etc.) are numeric hidden field values already present in the page, and the change only affects internal JS comparison logic, not DOM output escaping.
- **Broken Access Control / Authn**: Not applicable — no access control or authentication logic is modified.
- **Insecure Design**: The change does not alter any security-relevant design decision. Note that this logic is still client-side, so a malicious user could manipulate hidden field values via browser dev tools to alter displayed payment calculations — but this is a pre-existing trust boundary issue (client-side computed display values should never be trusted for actual billing/payment posting), not something introduced by this diff. If the *displayed* adjustment/remainder values are ever used server-side without re-validation upon form submission, that would be a pre-existing insecure design concern (trusting client-computed amounts), but this diff does not change that trust boundary — it only fixes a display calculation bug.

**Recommendation (not blocking this PR):** Verify separately (outside this diff) that the actual payment amounts posted to the server (`HiddenIns`, `AdjAmount`, `RemainderTd`, etc.) are re-validated and recalculated server-side before being persisted to the database, since client-side JS (as seen here) should not be the authoritative source for financial calculations.

**Conclusion:** No actionable security issues in this specific diff. Safe to merge from a security perspective.