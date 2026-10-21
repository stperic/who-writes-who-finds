## Review: `library/payment_jav.inc.php` (JavaScript comparison fix)

**Verdict: No security vulnerabilities introduced.** This change is a correctness fix with no security impact on its own. I did note two observations below that are not vulnerabilities in this diff but are worth knowing.

### What the change does

The diff replaces two comparisons:

```js
document.getElementById('HiddenIns' + CountIndex).value === 1
```

with

```js
parseInt(document.getElementById('HiddenIns' + CountIndex).value, 10) === 1
```

DOM `.value` properties are always strings, so the original strict comparison against the number `1` could never be true. The primary-insurance branch was dead code. The change makes that branch reachable. The `parseInt(..., 10)` call with an explicit radix is the correct way to do this. Non-numeric input yields `NaN`, which fails the `=== 1` check and falls through to the `else` branch, so there is no unsafe default.

### OWASP Top 10 checklist

| Category | Finding |
|---|---|
| A01 Broken Access Control | None introduced. |
| A02 Cryptographic Failures | None. |
| A03 Injection (SQL/XSS/etc.) | None introduced. The only changed values are numeric comparisons. |
| A04 Insecure Design | None introduced. See observation 1 below. |
| A05 Security Misconfiguration | None. |
| A06 Vulnerable Components | None. No dependencies changed. |
| A07 Auth Failures | None. |
| A08 Integrity Failures | None introduced. See observation 1 below. |
| A09 Logging/Monitoring | None. |
| A10 SSRF | None. |

### Observations (not vulnerabilities in this diff)

1. **Behavior change in payment calculations (integrity / correctness, Low, informational).** The primary-insurance first-payment branch now executes. It recalculates `AdjAmount` and `RemainderTd` using `ChargeAmount` and `CopayAmount`, where previously it was always skipped. This is intended, but it changes displayed financial figures. Confirm that the branch was intended to run, and that the server-side posting logic (not shown in this diff) independently recomputes or validates adjustment and payment amounts. Client-side calculations are not a trust boundary and should not be relied on for integrity.

2. **Pre-existing `innerHTML` assignment (XSS risk, Informational).** Lines such as `document.getElementById('RemainderTd' + CountIndex).innerHTML = Math.round(...)` use `innerHTML` with a numeric value. The value is produced by arithmetic on `formatNumber(... * 1)` results, so it cannot carry markup, and `NaN` renders as the harmless string "NaN". This is not exploitable as written, but `textContent` would be the safer default if this code is touched again.

### Recommendation

Approve from a security standpoint. Optionally, add a test covering the primary-insurance branch now that it is reachable, and verify the server-side validation noted in observation 1.