# Security Review: portal_payment.php

## Critical Issues

### 1. Broken Access Control — Unauthenticated `$recid` lookup bypasses patient scoping
**Location:** `portal/portal_payment.php`, lines ~60-75
```php
$recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
...
if ($recid) {
    $edata = $appsql->getPortalAuditRec($recid);
} else {
    $edata = $appsql->getPortalAudit($pid, 'review', 'payment');
}
```
`$recid` is attacker-controlled and used to fetch an arbitrary payment-audit record **without verifying it belongs to `$pid`/the current session's patient**. A portal patient (where `$ignoreAuth = true` is set precisely because normal ACL checks are skipped) can enumerate `recid` values and pull another patient's `$edata`, which includes decrypted credit card data (`$ccdata`) and invoice data (`$invdata`), displayed later in the page (name on card, zip, card number, expiry, CVV depending on auth state). This is a textbook IDOR / broken access control vulnerability, compounded by the fact that `$ignoreAuth` is explicitly in play for the portal flow.
**Severity: Critical** — direct unauthorized disclosure of cardholder data (PAN, CVV in non-redacted cases) and PII across patients.

---

### 2. Cryptographic Failures — Storage and display of full PAN and CVV
**Location:** Multiple, e.g.
```php
echo $ccdata["cardNumber"] . "</span><br>";
...
<span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?></span>
```
The application stores encrypted credit card data (`decryptStandard($edata['checksum'])`) that includes full PAN and **CVV**, and displays the **full PAN and CVV in cleartext** to authenticated staff (`$_SESSION['authUserID']`), and even to the patient for a trailing portion (`$_SESSION['authUserID']) || isset($ccdata["transId"])`). Storing CVV at all (even encrypted) is a PCI-DSS violation — CVV must never be persisted after authorization. Combined with issue #1, this data is also exposed to the wrong patient entirely.
**Severity: Critical** (PCI-DSS CVV storage violation + exposure amplified by IDOR above).

---

### 3. Injection / Logic Flaw — `$_SESSION['authId']` vs `$_SESSION['authUserID']` inconsistency in copay insert
**Location:**
```php
$session_id = sqlInsert(
    "INSERT INTO ar_session (payer_id,user_id,reference,...) VALUES ('0',?,?,...)",
    array($_SESSION['authId'], $form_source, $amount, $form_pid, $form_method)
);
```
Not strictly an injection (parameterized), but `$_SESSION['authId']` appears to be the wrong/non-existent session key (elsewhere the code uses `$_SESSION['authUserID']`). This likely always inserts NULL for `user_id`, which is a data-integrity / audit-logging problem — financial transactions cannot be attributed to a user. This weakens logging/monitoring and non-repudiation for payment postings.
**Severity: Medium** (audit integrity, not exploitable directly but undermines accountability).

---

### 4. Broken Access Control — `radio_type_of_payment` / encounter / amount fully client-controlled with no server-side authorization or amount validation
**Location:** entire `$_POST['form_save']` handling block.
The server trusts `$_POST['form_upay'][$enc]` (encounter → amount) and `$_REQUEST['radio_type_of_payment']` without:
- Verifying the encounter (`$enc`) belongs to `$form_pid` (the query filters by `pid` and `encounter` together in some places, so there's partial protection, but the initial trust boundary is still only `$pid` matching session `$pid`/`hidden_patient_code` which is client-supplied — see #5).
- Validating that `$amount` does not exceed the actual balance due (there is a comparison in JS only — `calctotal()`/`coloring()` — which is **client-side** and trivially bypassed via direct POST to this script).
This allows a portal user to submit arbitrary payment amounts/adjustments into `ar_activity`/`ar_session`, potentially creating incorrect financial records, negative adjustments, or posting a "payment" of any value against any encounter/invoice they can reference.
**Severity: High**

---

### 5. Broken Access Control — `$pid` can be overridden by request parameters even in portal context
**Location:**
```php
$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
```
This runs **after** `$pid = $_SESSION['pid']` was set for portal users. Because `$ignoreAuth = true` for the portal path, normal ACL (`acl_check`)/ownership checks that would otherwise catch a mismatched pid are bypassed. If `$_REQUEST['pid']` or `hidden_patient_code'` is attacker-supplied and not re-validated against the session's own patient id before use in SQL/business logic, a logged-in portal patient could submit payments / view invoice data for a different patient ID. There's no visible check anywhere in the diff reconciling `$_REQUEST['pid']` against `$_SESSION['pid']` before it's used for `$patdata`, billing lookups, or payment insertion.
**Severity: Critical** (classic IDOR allowing cross-patient data access/payment manipulation).

---

### 6. SSRF / Server-side trust of client-provided gateway tokens
**Location:** AuthorizeNet / Stripe JS blocks and `./lib/paylib.php` (not in diff, but relied upon)
The client sends `dataDescriptor`/`dataValue` (AuthorizeNet opaque token) or `stripeToken` to `paylib.php`. This is reviewed code's contract with an external file not shown, but worth flagging: the payment amount (`paymentAmount`) is also sent from the client (`$("#paymentAmount").val(total)` sourced from client-side JS `calctotal()`), meaning **the amount charged to the gateway may be attacker-controlled** unless `paylib.php` revalidates server-side against the actual invoice balance. Given this file computes `$sum_balance`/`$sum_duept` server side but then still relies on client POST `form_paytotal`/`paymentAmount` for the actual charge, this is a strong risk of payment-amount tampering.
**Severity: High** (unconfirmed without `paylib.php`, but the trust model here is unsafe — flagging as a design issue this PR relies on).

---

### 7. Insecure Design — Hardcoded test credit card year list / expired test data left in a production payment form
**Location:**
```php
<option value="2019">2019</option>
...
```
Minor, but the year dropdown contains already-expired years (2019–2021 at time of many deployments) — a sign the form wasn't properly reviewed for a production financial flow. Not itself a vulnerability but indicates insufficient review rigor for payment-handling code.
**Severity: Low**

---

### 8. Security Misconfiguration — Secrets echoed into page/JS context
**Location:**
```php
var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
```
`gateway_api_key` is documented in `globals.inc.php` as "The Auth Name or API key for selected account... Auth Name for Authorize.Net and API Secret for Stripe". For Stripe, this configuration value is described as a **secret key**, and if misconfigured/reused as the secret (rather than publishable) key it would be fully exposed client-side to any portal user viewing page source. Even for Authorize.Net, where `apiLoginID` is meant to be public-ish, mixing "API Login Auth Name or Secret" into one global used for both gateways is a dangerous configuration pattern that risks accidental secret leakage to the browser.
**Severity: High** (risk of full payment-gateway secret key disclosure depending on operator configuration).

---

### 9. XSS — residual risk around `text()`/`attr()` usage inconsistency
**Location:** various `echo $ccdata["cardNumber"]` (unescaped) vs `text($ccdata["cc_type"])` (escaped) in the same block:
```php
if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) {
    echo $ccdata["cardNumber"] . "</span><br>";
} else {
    echo "**********  " . substr($ccdata["cardNumber"], -4) . "</span><br>";
}
```
`$ccdata["cardNumber"]` is echoed **without any output encoding** (`text()`/`attr()`/`htmlspecialchars`), unlike nearly every other field in the same area. Since `$ccdata` is attacker-reachable data (originating from JSON-decoded, user-submitted payment-form fields persisted via `paylib.php`, not server-generated constants), this is a stored XSS vector if a card-number field is ever populated with HTML/script content instead of being digit-validated server-side before storage. Combined with issue #1 (arbitrary `recid`), an attacker could potentially plant malicious "card number" content and have it rendered unescaped to another victim's/admin's session.
**Severity: High** (stored XSS potential, severity amplified by the IDOR in #1 allowing cross-user delivery).

---

### 10. Logging/Monitoring — no logging of payment authorization/override actions
**Location:** Entire payment posting flow.
Sensitive actions (posting a payment, authorizing a pending card payment via `getAuth()`/`check_number`) have no visible audit-log calls (e.g., no `newEvent`/`EventAuditLogger` invocation) distinguishing this from standard OpenEMR financial actions elsewhere in the codebase. Given the cross-patient IDOR risk above, lack of logging means such abuse would be difficult to detect or investigate after the fact.
**Severity: Medium**

---

### 11. Pre-existing issue (relied upon, not introduced) — `$ignoreAuth` bypass pattern
**Location:** top of file, pre-existing but central to all above
```php
if (isset($_SESSION['pid']) && isset($_SESSION['patient_portal_onsite_two'])) {
    $pid = $_SESSION['pid'];
    $ignoreAuth = true;
```
This pattern, pre-existing in the codebase, disables standard ACL enforcement for the entire script whenever portal session variables are set. All the new code added in this PR (the `$recid` lookup, the payment posting) inherits this already-weakened trust boundary. This is not new in this diff but is a necessary precondition for several of the findings above and should be reviewed/hardened (e.g., strict server-side reconciliation of `$pid` with `$_SESSION['pid']` and never trusting `$_REQUEST['pid']` to override it).
**Severity: High (pre-existing, but directly enables new vulnerabilities above)**

---

## Summary Table

| # | Location | OWASP Category | Problem | Severity |
|---|----------|----------------|---------|----------|
| 1 | `$recid`/`getPortalAuditRec` | A01 Broken Access Control (IDOR) | No ownership check tying `recid` to session patient | Critical |
| 2 | ccdata rendering | A02 Cryptographic Failures | Full PAN/CVV stored & displayed in clear | Critical |
| 3 | `$_SESSION['authId']` | A09 Logging/Integrity | Wrong session key, loses audit attribution | Medium |
| 4 | form_upay posting | A01 Broken Access Control | No server-side amount/balance validation | High |
| 5 | `$pid` override via `$_REQUEST` | A01 Broken Access Control (IDOR) | Client can override patient ID under `$ignoreAuth` | Critical |
| 6 | paylib.php payment amount | A04 Insecure Design / SSRF-adjacent | Client-supplied charge amount trusted | High |
| 7 | CC year list | Insecure Design | Minor QA issue, expired years | Low |
| 8 | `gateway_api_key` in JS | A05 Security Misconfiguration | Possible secret key leaked to browser | High |
| 9 | `$ccdata["cardNumber"]` unescaped | A03 Injection (XSS) | Missing output encoding on untrusted field | High |
| 10 | payment posting | A09 Logging & Monitoring Failures | No audit trail for payment actions | Medium |
| 11 | `$ignoreAuth` top of file | A01 Broken Access Control | Pre-existing ACL bypass pattern enabling above | High |

**Recommendation priority:** Fix #1/#5 (IDOR/pid trust) first — they are root causes amplifying nearly every other finding — then address CVV storage (#2) and the client-controlled payment amount (#6) before this is production-safe for handling real payments.