## Security review: `library/payment_jav.inc.php`

**Result: no security vulnerabilities found in this diff.**

### What the change does
The diff replaces `element.value === 1` with `parseInt(element.value, 10) === 1` in two places. An input's `.value` is always a string, so the old strict comparison against the number `1` was always false. The new code parses the string first, so the "primary's first payment" branch can now run. This is a functional bug fix, not a security change.

### Checklist
| OWASP category | Finding |
|---|---|
| Injection / XSS | None. The `innerHTML` assignments receive the output of `Math.round(...)`, which is always a number (or `NaN`), never a string. The `parseInt` change doesn't alter what gets written. `innerHTML` is not an exploitable sink here, though `textContent` would be a cleaner choice. |
| Broken access control, authentication, SSRF, cryptography, components, logging | Not affected. The change is a client-side comparison only. |
| Insecure design / data integrity | No new risk. These values are computed in the browser purely for display and convenience. |

### Non-blocking notes
- **Behavior change:** The primary-first-payment branch was effectively dead code and will now execute. The remainder and adjustment amounts shown to users will change for primary-insurance rows. Please check that this is intended and that a reviewer or QA has verified the numbers. This is a correctness concern, not a security one.
- **Server-side validation (existing practice, not part of this diff):** Payment, adjustment, and remainder amounts calculated in JavaScript must never be trusted by the server. Confirm that the server recomputes or validates them on submission, along with CSRF protection and authorization on the posting endpoint.
- **Minor:** Consider using `textContent` instead of `innerHTML` for numeric output as a defense-in-depth habit.

**Severity:** none. Safe to merge from a security standpoint.