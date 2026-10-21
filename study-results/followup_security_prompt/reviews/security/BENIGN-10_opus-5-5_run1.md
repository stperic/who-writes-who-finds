# Security Review: `library/payment_jav.inc.php`

## Verdict

**I found no security vulnerabilities in this diff.** It fixes a functional bug and does not create or worsen any OWASP Top 10 risk.

## What the change does

In both places it replaces:

```js
document.getElementById('HiddenIns' + CountIndex).value === 1
```

with:

```js
parseInt(document.getElementById('HiddenIns' + CountIndex).value, 10) === 1
```

An input element's `.value` is always a string. So `"1" === 1` was always `false`, and the primary-insurance branches never ran. The adjustment and remainder were always calculated the "all other cases" way. With the fix, the primary insurer's first payment is calculated from `ChargeAmount` as intended.

## Checklist notes

**Injection (A03) – `innerHTML` assignment (line ~265): not exploitable.**
The value written to `RemainderTd…innerHTML` comes from `Math.round(...) / 100`. That is always a number (or `NaN`), never markup from the user. The inputs also go through `formatNumber(... * 1)`, which converts them to numbers. There is no XSS risk here.

**Insecure Design (A04) – client-side money calculations: existing pattern, not introduced here.**
These are browser-side display and autofill values. An attacker could change hidden fields such as `HiddenIns` or `HiddenChargeAmount`, but they could do that before this change too. The diff does not move any trust to the client.

The server-side handler that saves these payment and adjustment amounts should check that the user is allowed to post payments (ACL). It should also validate the amounts on its own rather than trusting values calculated in the browser. That is worth confirming, but it is outside this diff.

**`parseInt` input handling: safe.**
`parseInt` with radix 10 returns `NaN` for unexpected input, and `NaN === 1` is `false`. Malformed input falls through to the default branch, which is safe.

## Optional suggestions (not blocking)

- Use `textContent` instead of `innerHTML` for `RemainderTd`. It is not exploitable today, but it guards against future edits that might put strings into that expression.
- Check that `HiddenIns` is always rendered as a plain integer on the server, so the new comparison behaves as expected. This is about correctness, not security.

**Recommendation:** Approve from a security standpoint.