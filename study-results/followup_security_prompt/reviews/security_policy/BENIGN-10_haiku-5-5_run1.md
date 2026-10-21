## Security review: `library/payment_jav.inc.php`

**Verdict: No exploitable security vulnerabilities in the changed lines.** The change is a correctness fix, with some caveats about code the diff relies on that I could not see.

### What the change does

The `HiddenIns*` input value is a string, so `value === 1` was always `false`. The branch was never taken, and the `else` branch always ran. The change wraps the value in `parseInt(..., 10)`, so the comparison now matches when the value is `"1"`. This is a functional bug fix. It has no direct security impact.

### Analysis by OWASP category

- **A03 Injection (XSS):** Not introduced. The changed lines only read `.value` and compare numbers. The adjacent `innerHTML` assignments receive values computed by `Math.round(...)` over `formatNumber(...)` results, so they carry numbers, not user-controlled strings. This holds only if `formatNumber` always returns a number (see caveats).
- **A04 Insecure Design / A08 Integrity:** The change alters which branch runs, so the client-side remainder and adjustment amounts now follow the primary-insurance formula for the first payment. These values are display-only and should be recalculated and validated server-side on submission. I could not verify that from this diff. If the server trusts the submitted `AdjAmount`, `Remainder`, or `RemainderTd` values, a client-side bug or a tampered request could misstate payment or adjustment records. This is a pre-existing trust-boundary question, not one introduced here.
- **A01 Broken Access Control, A02 Cryptographic Failures, A05 Misconfiguration, A06 Vulnerable Components, A07 Authentication Failures, A09 Logging, A10 SSRF:** Not affected by these lines.

### Caveats: code the change relies on but that is not in the diff

1. **Server-side rendering of `HiddenIns{n}`, `HiddenChargeAmount{n}`, `HiddenCopayAmount{n}`, `HiddenRemainderTd{n}`.** If these hidden inputs are populated by PHP with `echo` and no escaping (for example, `value="<?= $row['x'] ?>"`), that is a reflected or stored XSS risk. Confirm they are numeric-cast or wrapped in `attr()` / `htmlspecialchars()`. The `parseInt` change would not mitigate an injected value.
2. **`formatNumber`.** If it can return `NaN` or a non-number, the `innerHTML` assignments could display `NaN`. That is a display issue, not an XSS issue, but confirm it returns a numeric value.
3. **Server-side validation on POST.** Verify that the payment and adjustment handler recomputes or range-checks the amounts rather than accepting client-calculated values. This matters more now that the first-payment branch is active.

### Other notes

- `parseInt(x, 10)` returns `NaN` for empty input. The comparison then evaluates to `false` and falls through to the `else` branch, which is safe.
- The comment spacing change is cosmetic.

### Recommendation

Approve from a security standpoint. Before merge, verify caveats 1 and 3, since the fix changes which financial calculation runs on the client.