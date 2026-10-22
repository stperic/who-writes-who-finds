## Summary

This diff bundles a large formatting/whitespace cleanup together with several functional changes (new `recid` lookup path, new payment-gateway tokenization flows, sequence_no handling, UI markup changes). Below are the issues I'd raise, ordered roughly by severity.

---

### 1. IDOR: `recid` lookup does not verify ownership
**Location:** 
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
...
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
} else {
    $edata = $appsql->getPortalAudit($pid, 'review', 'payment');
}
```
**Problem:** `$recid` comes straight from user input and is used to fetch an audit record by primary key with no check that the record belongs to `$pid`/the current session. A patient (or anyone with a valid portal session) can enumerate `recid` values and pull back another patient's payment audit record — including encrypted card data (`checksum`) that is subsequently decrypted and rendered (card type, last 4 digits, invoice totals, patient name context, etc.). This is a broken access control / IDOR vulnerability.
**Severity:** High/Critical — must validate `$edata['pid'] == $pid` (or equivalent) before using the record.

---

### 2. Full card number / CVV exposure logic is weakened
**Location:**
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```
**Problem:** Previously, the full PAN was only displayed when an authenticated staff user (`authUserID`) viewed the record. The new `|| isset($ccdata["transId"])` clause means the full card number can now be rendered to a non-staff (patient) session whenever a `transId` is present. Combined with CVV (`cardCode`) also being echoed elsewhere in the same panel, this is a PCI-DSS violation (CVV must never be retained/displayed after authorization, and full PAN display should be restricted to need-to-know roles).
**Severity:** High — recommend always masking PAN/CVV except for a legitimately scoped admin view, and never storing/displaying CVV at all.

---

### 3. Possible exposure of gateway secret via client-side JS
**Location:**
```php
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
**Problem:** `gateway_api_key` is embedded directly in page source. If this global actually holds a secret/transaction key (rather than a public API Login ID intended for Accept.js tokenization), this leaks merchant credentials to anyone viewing page source.
**Severity:** Medium/High depending on what `gateway_api_key` actually stores — worth explicit verification/comment in code.

---

### 4. Race condition in manual `sequence_no` computation
**Location:** (repeated 3 times, e.g.)
```php
sqlBeginTrans();
$sequence_no = sqlQuery("SELECT IFNULL(MAX(sequence_no),0) + 1 AS increment FROM ar_activity WHERE pid = ? AND encounter = ?", ...);
sqlInsert(...);
sqlCommitTrans();
```
**Problem:** Without a `SELECT ... FOR UPDATE` (row/gap lock) or a unique constraint + retry, two concurrent requests (e.g., a double-click/retry from the portal) can compute the same `sequence_no`, leading to duplicate sequence numbers or a constraint violation that isn't handled. `sqlBeginTrans`/`sqlCommitTrans` alone don't prevent this under default MySQL isolation.
**Severity:** Medium — financial/billing data integrity risk.

---

### 5. Inconsistent/likely-wrong session variable used for `post_user`
**Location:**
```php
$insrt_id = sqlInsert(
    "INSERT INTO ar_activity (... post_user ...) VALUES (...)",
    array($form_pid, $enc, $sequence_no['increment'], $Codetype, $Code, $Modifier, $_SESSION['authId'], $session_id, $amount)
);
```
**Problem:** Everywhere else in this file (and the rest of OpenEMR) uses `$_SESSION['authUserID']`. `$_SESSION['authId']` doesn't appear to be a standard session key, so this will likely insert `NULL`/empty `post_user`, breaking audit trail consistency for copay postings while other payment paths correctly populate it.
**Severity:** Medium (correctness/auditability bug).

---

### 6. Malformed `<tr>` markup
**Location:**
```php
<?php if (isset($_SESSION['authUserID'])) {
        $hide = '';
        echo '<tr height="5"><td colspan="3"></td></tr><tr">';
} else {
    $hide = 'hidden';
    echo '<tr class="hidden">';
}
?>
```
**Problem:** `'<tr height="5">...</tr><tr">'` has a stray `"` with no attribute name — invalid HTML (`<tr">`). Browsers will likely recover, but this is clearly a typo and should be `<tr>`.
**Severity:** Low/Medium (functional HTML bug, could break row visibility toggling depending on parser).

---

### 7. Payment-method filter condition is a no-op for the new branch
**Location:**
```php
if ($brow1112['option_id'] != 'credit_card' || $brow1112['option_id'] == 'debit' || $brow1112['option_id'] == 'bank_draft') {
    continue;
}
```
**Problem:** Boolean logic is broken (carried over from the previous version, just swapping `electronic` for `debit`): since an option can't simultaneously equal `'credit_card'` and `'debit'`/`'bank_draft'`, the second and third clauses never actually change the outcome — only rows exactly equal to `'credit_card'` are ever shown. This likely isn't the intended behavior (seems intended to allow `credit_card`, `debit`, and `bank_draft` options). This is a pre-existing bug that this PR perpetuates rather than fixes.
**Severity:** Low/Medium (dead code / functional bug, worth fixing while touching this line).

---

### 8. Code duplication for `ar_activity` insert + sequence_no logic
**Location:** Three near-identical blocks (copay insert, per-code insert in the loop, "excess amount" insert).
**Problem:** The sequence-number + insert pattern is duplicated three times with only minor parameter differences. This increases maintenance burden and risk of divergent bugs (as seen in issue #5, where one copy uses `authId` and others use `authUserID`).
**Severity:** Low (maintainability).

---

### 9. Minor/cosmetic
- `$isPortal = true;` is introduced but not used anywhere in the shown diff — dead code (Low).
- `$ccdata['authCode']` / `$ccdata['transId']` accessed without `isset()` checks, will raise PHP notices (Low).
- Global mutable state (`$sum_charges`, etc.) used inside `echoLine()` makes the function non-reentrant/order-dependent — acceptable for this script's scope but worth a comment (Low).
- Hardcoded expiration year list (2019–2028) will need periodic manual updates instead of being generated dynamically (Low).
- No CSRF token on `invoiceForm`/`paymentForm` submission to `paylib.php` (pre-existing, but since this PR touches the payment flow significantly, worth calling out) (Medium, pre-existing).

---

## Recommendation
Before merging: at minimum fix #1 (IDOR on `recid`) and #2 (card data exposure) since they are security-sensitive and directly related to new code added in this PR. #4/#5 should be fixed for data integrity. The rest can be tracked as follow-up cleanup.