## Review Comments

### 1. Insecure Direct Object Reference via `recid` (Critical – Security)
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
`$recid` is taken straight from the request and used to fetch an arbitrary audit/payment record (which contains decrypted card data, CVV, etc.) with no check that the record belongs to `$pid`/the current session patient. Unless `getPortalAuditRec()` internally enforces ownership (not shown), any authenticated portal user (or anyone who can reach this endpoint) could view another patient's stored payment details by simply changing `recid`. This needs an explicit `WHERE pid = ?` constraint or a post-fetch ownership check.

The new `$isPortal` flag is set but never used anywhere in the diff — it looks like it was intended to gate this kind of access but the check was never wired in.

### 2. Payment gateway secret key sent to the browser (Critical – Security)
**Location:**
```js
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
This is emitted unconditionally, regardless of which `payment_gateway` is configured. Per `globals.inc.php`, `gateway_api_key` holds **"Auth Name for Authorize.Net and API Secret for Stripe"**. When Stripe is configured, this line leaks the Stripe **secret key** directly into page source for any visitor of this page (patient or otherwise), enabling attackers to perform arbitrary operations against the merchant's Stripe account. Even for non-Stripe configurations, there's no reason to always echo this value — it should only be emitted when actually required by the active gateway's client code, and never if it is a secret/non-public value.

### 3. CVV being stored and displayed (Critical – Security / PCI-DSS)
**Location:**
```php
<strong><?php echo xlt('CVV'); ?>:  </strong><span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?></span><br>
```
Persisting and redisplaying the card security code (CVV) after initial authorization is a direct PCI-DSS violation. This data should never be stored past the authorization transaction, let alone rendered back to the UI.

### 4. Full card number can be revealed to unauthenticated patient context (High – Security)
**Location:**
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```
Previously the masking was based solely on `authUserID`. Now `isset($ccdata["transId"])` also unmasks the full card number even when there is no authenticated admin session (i.e., for the patient-facing view). This weakens the masking logic and should be reviewed — full card numbers should essentially never be stored/displayed at all.

### 5. Likely wrong/undefined session variable for `post_user` (Medium – Correctness)
**Location:**
```php
$insrt_id=sqlInsert(
    "INSERT INTO ar_activity (pid,encounter,sequence_no,code_type,code,modifier,payer_type,post_time,post_user,session_id,pay_amount,account_code)".
    " VALUES (?,?,?,?,?,?,0,now(),?,?,?,'PCP')",
    array($form_pid, $enc, $sequence_no['increment'], $Codetype, $Code, $Modifier, $_SESSION['authId'], $session_id, $amount)
);
```
Elsewhere in this same file the session key used consistently is `$_SESSION['authUserID']`; `$_SESSION['authId']` does not appear to be set anywhere. This will likely insert `NULL`/empty for `post_user`, corrupting the audit trail for who posted the payment.

### 6. Sequence number generation is not race-safe (Medium – Reliability)
**Location (repeated 3x):**
```php
sqlBeginTrans();
$sequence_no = sqlQuery("SELECT IFNULL(MAX(sequence_no),0) + 1 AS increment FROM ar_activity WHERE pid = ? AND encounter = ?", array($form_pid, $enc));
sqlStatement("insert into ar_activity ...", array(..., $sequence_no['increment'], ...));
sqlCommitTrans();
```
Wrapping a plain `SELECT MAX()+1` / `INSERT` in a transaction does not prevent two concurrent requests from reading the same max value before either commits (no `SELECT ... FOR UPDATE`, no unique constraint enforcement shown). Under concurrent payment submissions this can produce duplicate `sequence_no` values.

### 7. Malformed HTML tag (Medium – Correctness/UI bug)
**Location:**
```php
echo '<tr height="5"><td colspan="3"></td></tr><tr">';
```
This emits `<tr">` instead of `<tr>` — a stray double-quote is left in the markup, resulting in invalid HTML and potentially a visibly broken table row.

### 8. Duplicate element IDs across forms (Medium – Maintainability/Correctness)
**Location:** `invoiceForm`, `paymentForm`, and `payment-form` (Stripe) all contain:
```html
<input type='hidden' name='mode' id='mode' value=''/>
```
Having multiple elements with the same `id="mode"` is invalid HTML. `$("#mode")`/`document.getElementById("mode")` calls will silently only ever affect the first matching element in DOM order. The code currently appears to "work" because of DOM ordering, but this is fragile — any reordering of the markup will silently break payment mode submission.

### 9. Reduced client-side validation (Low)
**Location:** Credit card fields (`cardHolderName`, `cardNumber`, `cardCode`) had their `required`/`pattern` attributes removed compared to the prior version (e.g., `cardCode` lost `maxlength`/`pattern="\d{3}"` strictness, `required` dropped on several fields). This relies more heavily on server-side validation; worth confirming `paylib.php` fully re-validates these fields.

### 10. Hardcoded expiry year list will need yearly maintenance (Low)
**Location:**
```html
<option value="2019">2019</option>
...
<option value="2028">2028</option>
```
This list will begin rejecting valid cards once the current year passes the last listed year. Consider generating this dynamically (e.g., `date('Y')` + N years).

### 11. Silent behavior change: default selected payment type (Informational)
**Location:**
```html
<input type="radio" ... id="radio_type_of_payment1" ... value="copay" .../>
<input type="radio" ... id="radio_type_of_payment2" checked="checked" value="invoice_balance" .../>
```
Previously "Co Pay" (`radio_type_of_payment1`) was `checked` by default; now "Invoice Balance" is the default selection. If unintentional, this changes default behavior for all users; worth confirming this was deliberate.

---
No issues found with the majority of the JS variable renames (`payfrm` → `invoiceForm`, `paycredit` → `paymentForm`) or the totals-row refactor (`echoLine` accumulating sums) — these look correct and are a reasonable cleanup. The main concerns are the security-sensitive items (#1–#4), which should block merge until addressed.