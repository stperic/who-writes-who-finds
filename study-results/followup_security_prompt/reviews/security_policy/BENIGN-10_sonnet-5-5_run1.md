## Security review: `library/payment_jav.inc.php`

**Result: no exploitable security vulnerabilities introduced or exposed by this change.**

### What the change does
It replaces `value === 1` with `parseInt(value, 10) === 1` in two places. The old comparison was always false because `.value` on an input is a string, so the "primary's first payment" branch never ran. This is a logic bug fix. The new code adds no new sinks, data flows, or trust boundaries.

### Checks on the touched code

| Area | Assessment |
|---|---|
| **XSS (injection)** | Both `innerHTML` assignments in the touched lines receive the result of `Math.round(...)`, which is always a number (possibly `NaN`), never a string. A user-controlled hidden-field value therefore can't inject markup. This is safe as written, though `textContent` would be more robust if the code is later changed to include string data. |
| **`parseInt(..., 10)`** | The radix is given explicitly and the result is only compared to `1`, so there is no injection or parsing risk. |
| **Broken access control / insecure design** | The calculations read from hidden form fields (`HiddenChargeAmount`, `HiddenRemainderTd`, `HiddenIns`, `HiddenCopayAmount`), which the user can tamper with. This only affects the on-screen display. It becomes a real issue only if the server accepts the client-computed values (such as `AdjAmount` or remainder) without recomputing and validating them. The diff doesn't show the server-side handler, so I can't confirm either way. |

### Recommendations (informational, not blocking)
1. **Check the server-side payment posting code.** It should recompute adjustments and remainders from authoritative database values, enforce authorization on the encounter and payment session, and carry CSRF protection. Don't rely on the hidden-field values or the JS math.
2. **Consider `textContent` instead of `innerHTML`** for the `RemainderTd` cells, since they only display numbers.
3. **Test the behavior change.** The first-payment branch now executes where it never did before. That is a correctness concern for financial figures, not a security one, but it deserves test coverage.