# Review: `Recorder::getNextSequenceNumber()`

Overall this is a reasonable hardening change: it adds explicit failure handling and a more accurate return type. I have no blocking issues. The items below are mostly things to verify or tighten.

---

### 1. Return type changed from `string` to `int`: verify all call sites
**Location:** method signature, line ~207
**Severity:** Medium (verify before merge)

The method is private, so the impact is limited to `Recorder`. Still, check every caller in the class:
- **Strict-mode type errors:** If the file uses `declare(strict_types=1)` and the result is passed to a parameter typed `string`, that call now throws a `TypeError`.
- **Strict comparisons:** Any `===` or `!==` comparison against a string value (e.g. `$seq === '1'`, or comparison with another DB-fetched value, which drivers usually return as strings) will now silently evaluate differently.
- **String-only operations:** Uses such as `str_pad` or array-key logic are probably fine because of juggling, but they are worth a quick look.

If the only consumer is the bound parameter of the subsequent `INSERT`, this is safe.

---

### 2. `is_numeric()` is looser than needed
**Location:** `if (!is_numeric($increment))`
**Severity:** Low

`is_numeric` accepts values like `"1.5"`, `"1e3"`, `" 12"`, and negative numbers. The `(int)` cast then silently truncates or converts them. The query is `MAX(int) + 1`, so this shouldn't happen in practice. However, since the point of the change is validation, a stricter check would better express the intent:

```php
$increment = filter_var($result['increment'] ?? null, FILTER_VALIDATE_INT, ['options' => ['min_range' => 1]]);
if ($increment === false) {
    throw new \RuntimeException(...);
}
return $increment;
```

This also guarantees a positive integer, which is the actual invariant here.

---

### 3. Exception lacks diagnostic context
**Location:** `throw new \RuntimeException(...)`
**Severity:** Low

The message doesn't say which encounter failed, so it will be hard to debug from logs. Consider including the encounter ID. Be cautious about putting the patient ID in exception messages if they end up in logs or error pages, because it is patient-identifying data. Also check that callers handle this exception. In particular, if this runs inside a transaction, confirm the transaction is rolled back rather than left open.

---

### 4. Known race condition remains unaddressed
**Location:** comment above the method (pre-existing)
**Severity:** Medium (pre-existing, not introduced by this PR)

The comment already notes that `SELECT MAX()+1` followed by a separate `INSERT` can produce duplicate `sequence_no` values under concurrent posting for the same patient and encounter. This PR touches the method but doesn't fix that.

This is not a blocker for this change. Please make sure it is tracked, for example:
- with `SELECT ... FOR UPDATE` inside the transaction, or
- by computing the value in the `INSERT ... SELECT`, or
- with a unique constraint on `(pid, encounter, sequence_no)` plus a retry.

If the work is deferred, link a ticket from the comment.

---

### 5. No tests
**Severity:** Low

There are no tests for:
- the new failure path (query returns `false`/`null`, or the column is missing), and
- the normal path returning an `int`.

A small unit test with a mocked or stubbed query result would lock in the behavior.

---

**Summary:** Approve after confirming the callers are compatible with `int` (item 1). Items 2, 3 and 5 are optional improvements. Item 4 is pre-existing tech debt that should be tracked.