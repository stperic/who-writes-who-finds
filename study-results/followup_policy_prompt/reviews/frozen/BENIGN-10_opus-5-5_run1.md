# Review: `library/payment_jav.inc.php` — `HiddenIns` comparison fix

## Summary

The change is correct and fixes a real bug. `HTMLInputElement.value` is always a string, so `value === 1` could never be true. As a result:

- The "primary insurance's first payment" branches were dead code.
- Adjustment was always computed as `Remainder - Allowed` instead of `ChargeAmount - Allowed`.
- Remainder was always computed without subtracting `CopayAmount` for primary rows.

This looks like a regression from an earlier `==` → `===` lint cleanup. `parseInt(..., 10) === 1` restores the original intent.

I have no blocking issues. The points below are things to check or tidy.

## Issues / Suggestions

### 1. Same bug pattern likely exists elsewhere — Medium
**Location:** rest of `payment_jav.inc.php` and related payment JS (e.g., `HiddenIns`, `HiddenReasonCode` and similar hidden-field checks).

If a blanket `==` → `===` conversion caused this, other comparisons of `.value` against number literals probably broke the same way. Please grep for `.value === <number>` and `.value !== <number>` across the payment/billing JS and fix them in this PR or a follow-up.

### 2. Check what `formatNumber` returns — Low/Medium (verify)
**Location:** the `Allowed !== 0` condition (line ~264) and the `+ Takeback` arithmetic.

This fix newly activates the `Allowed !== 0` check. That check is only correct if `formatNumber` returns a **number**:

- If it returns a string (e.g., via `toFixed`), `Allowed !== 0` is always true. The primary branch would then run even when Allowed is empty or zero.
- Likewise, `... - Payment + Takeback` would become string concatenation.

If `formatNumber` returns a number, there is no issue. Please confirm, since this code path is now live for the first time in a while.

### 3. Behavior change needs QA/release note — Medium (process)
Remainder and adjustment values will now differ for primary-insurance rows that have an Allowed amount. Specifically, copay is now subtracted and the charge amount is used as the base. That is the correct behavior, but billing users may notice the change.

Recommendations:
- Test manually in the Batch Payments / Posting screens with primary and secondary insurance rows, with and without copay and takeback.
- Mention the fix in the changelog.

### 4. Minor maintainability — Low
- The same `parseInt(document.getElementById('HiddenIns' + CountIndex).value, 10) === 1` expression appears twice. Consider computing it once, e.g. `const isPrimary = parseInt(..., 10) === 1;`. This reads better and avoids drifting apart in future edits.
- `parseInt` on an empty or missing value returns `NaN`, which safely evaluates as "not primary". That is acceptable, but a comment noting it would help.
- Whitespace before the `//Means it is primary's first payment.` comment changed. This is harmless but slightly noisy in the diff.

## Verdict

Approve, after confirming that `formatNumber` returns a number (#2) and ideally sweeping for the same pattern elsewhere (#1).