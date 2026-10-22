# Security Review: `portal/portal_payment.php`

**Recommendation: do not merge.** The change adds a new card-data exposure path (`recid`) and leaks gateway credentials. It also builds on existing access-control and PCI flaws that this page relies on and that remain unfixed.

---

## Critical

### 1. IDOR via the new `recid` parameter exposes decrypted card data
- **Location:** `$recid = (int) $_REQUEST['recid']` → `$appsql->getPortalAuditRec($recid)` → `json_decode(decryptStandard($edata['checksum']))`
- **Category:** A01 Broken Access Control
- **Problem:** Any portal patient can supply any `recid`. Nothing checks that the audit record belongs to `$_SESSION['pid']`. The record's encrypted card blob is decrypted and rendered in the payment panel.
  - The change also adds `|| isset($ccdata["transId"])` to the unmasking condition, so the **full card number** is shown to non-staff for processed records.
  - For other records, the CVV (`cardCode`) and expiry are printed, regardless of user type.
- **Impact:** A patient can enumerate `recid` values and harvest other patients' names, ZIP codes, full card numbers, expiry dates and CVVs.
- **Fix:**
  - For portal sessions, ignore `recid`, or verify `audit.patient_id == $_SESSION['pid']`.
  - Never unmask the PAN based on `transId`.

### 2. Portal patients can override `pid` and view or post for any patient (pre-existing, relied upon)
- **Location:**
  - `$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;`
  - `$pid = $_REQUEST['hidden_patient_code'] > 0 ? ...`
  - `$form_pid = $_POST['form_pid']`
- **Category:** A01 Broken Access Control
- **Problem:** The session `pid` is replaced by request input even when `$isPortal` is true. A patient can view another patient's demographics, insurance copay, encounters, balances and card audit data by changing `pid`. The new `$isPortal` flag is set but never used to stop this.
- **Fix:** When `$isPortal`, force `$pid = $form_pid = $_SESSION['pid']` and reject any mismatch.

### 3. Portal patients can directly invoke the staff "Post Payment" logic (pre-existing)
- **Location:** `if ($_POST['form_save']) { ... }`
- **Category:** A01 Broken Access Control / A04 Insecure Design
- **Problem:** The save block is only hidden in the UI (the button renders only when `authUserID` is set). There is no server-side check. A portal user can POST `form_save` with:
  - `radio_type_of_payment=cash`, which runs `UPDATE billing SET billed=1` and `UPDATE form_encounter SET last_level_closed=4`;
  - or `pre_payment` / `invoice_balance`, which insert `ar_session` / `ar_activity` / `payments` rows.

  This lets a patient record fake payments and close out balances without paying, for any `form_pid` (see #2).
- **Fix:** Wrap the whole block in `if (!$isPortal && isset($_SESSION['authUserID']) && AclMain::aclCheckCore('acct','bill'))`.

### 4. Gateway secret leaked to the browser
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Category:** A02 Cryptographic Failures / A05 Security Misconfiguration
- **Problem:** This line is emitted for every gateway and every viewer. In OpenEMR, `gateway_api_key` is the "API Login / **Secret**" setting.
  - For Stripe it holds the **secret key**, giving full account control: charges, refunds and customer data.
  - For Authorize.Net the API Login ID is needed client-side. It is still unnecessary for the other gateways.
  - The global is an encrypted setting, so the raw ciphertext may also be leaked.
- **Fix:**
  - Only output `gateway_public_key` (plus the Authorize.Net login ID when that gateway is active, after decryption).
  - Never send the Stripe secret to the client.
  - Rotate the key if this has been deployed.

---

## High

### 5. Storing and displaying full PAN and CVV (InHouse mode; pre-existing, extended)
- **Location:**
  - The `paySubmit` flow posts `cardNumber`, `cardCode`, `month` and `year` to `paylib.php`, where they are stored encrypted in `onsite_portal_activity.checksum`.
  - The display code echoes `cardNumber` and `cardCode`.
- **Category:** A02 Cryptographic Failures / A04 Insecure Design
- **Problem:** PCI DSS forbids storing CVV/CVC after authorization in any form, and limits PAN display to those with a business need. Staff, and now patients via #1, see the full PAN and CVV. Encryption with an application-wide key that the web app decrypts on view gives little protection.
- **Fix:**
  - Remove or disable InHouse card capture in favour of tokenizing gateways.
  - Never persist `cardCode`.
  - Mask the PAN to the last 4 digits for all users.

### 6. Stored XSS through an unescaped card number
- **Location:** `echo $ccdata["cardNumber"] . "</span><br>";`
- **Category:** A03 Injection (XSS)
- **Problem:** `cardNumber` is attacker-controlled patient input (client-side `pattern` / `maxlength` are trivially bypassed). It is echoed raw on the staff audit view, and via #1 to other patients. A payload like `<script>…</script>` runs in a billing user's session, enabling account takeover and further fraudulent posting.
- **Fix:** Use `text()` (as is done for every neighbouring field) and validate server-side that the value is digits only.

### 7. No CSRF protection on financial state changes (pre-existing)
- **Location:** The `invoiceForm` POST to `portal_payment.php` and the `paylib.php` submissions.
- **Category:** A01 Broken Access Control (CSRF)
- **Problem:** No CSRF token is generated or checked. A malicious page can make a logged-in staff member's browser post payments, mark encounters billed and close them.
- **Fix:** Add `CsrfUtils::collectCsrfToken()` hidden fields and call `CsrfUtils::verifyCsrfToken()` before any write.

---

## Medium

### 8. No server-side validation of payment amounts
- **Location:** `$_REQUEST['form_prepayment']` and `$_POST['form_upay'][...]`
- **Category:** A04 Insecure Design
- **Problem:** The "Negative payments not accepted" check is JavaScript only. Negative, non-numeric or enormous amounts are written straight into `ar_session.pay_total`, `ar_activity.pay_amount` and `payments`. Combined with #3, this allows ledger manipulation.
- **Fix:** Validate server-side that amounts are positive decimals with 2 decimal places, within the invoice balance.

### 9. Receipt path trusts request input
- **Location:** `if ($_POST['form_save'] || $_REQUEST['receipt'])`, which uses `$form_pid` / `$payrow` from the request.
- **Category:** A01 Broken Access Control
- **Problem:** A portal user can request receipts for other patients' payments.
- **Fix:** Bind the receipt lookup to the session `pid` for portal users.

### 10. Missing or incorrect audit attribution for postings
- **Location:**
  - `user_id = $_SESSION['authUserID']` and `post_user = $_SESSION['authUserID']` (null for portal sessions).
  - `$_SESSION['authId']` is used inconsistently in the copay branch.
- **Category:** A09 Security Logging and Monitoring Failures
- **Problem:** Payments posted through the portal path (#3) are recorded with no user. Fraudulent entries cannot be traced. Patient-side posting attempts are not logged as security events.
- **Fix:**
  - Block portal posting.
  - Always record an actor.
  - Log denied attempts via `EventAuditLogger`.

---

## Low

### 11. Output-encoding inconsistencies
- **Category:** A03 Injection
- **Problems:**
  - `xlt('Invoice')` is used inside a `value='...'` attribute; it should be `xla`.
  - `xlt(...)` is used inside a JS `prompt("...")` string; it should be `xlj` or `json_encode`.
  - `addslashes(xl(...))` is used in JS strings.
  - `$GLOBALS['webroot']` and `$GLOBALS['assets_static_relative']` are echoed unescaped into URLs and JS.
- **Impact:** These are admin- or translation-controlled, so low risk, but they should be fixed with the correct helpers (`attr`, `js_escape`).

### 12. Dead `$isPortal` flag and UI-only gating
- **Category:** A04 Insecure Design
- **Problem:** The PR introduces `$isPortal` but relies on the CSS `hidden` class and conditional button rendering to separate patient and staff capabilities. This gives a false sense of protection; see #2 and #3.

### 13. Outdated or unpinned client components
- **Category:** A06 Vulnerable and Outdated Components
- **Problem:** `jquery-creditcardvalidator` is legacy. The new Accept.js / Stripe.js code depends on externally loaded scripts whose inclusion and integrity (SRI or CSP) are not visible here.
- **Fix:** Confirm they load from official HTTPS endpoints under a CSP.

---

## Summary

| # | Issue | OWASP | Severity |
|---|-------|-------|----------|
| 1 | `recid` IDOR, full PAN/CVV disclosure | A01 | Critical |
| 2 | `pid` override by portal user | A01 | Critical |
| 3 | Portal user can post payments / close billing | A01/A04 | Critical |
| 4 | `gateway_api_key` (Stripe secret) sent to browser | A02/A05 | Critical |
| 5 | PAN + CVV storage and display | A02/A04 | High |
| 6 | Stored XSS via `cardNumber` | A03 | High |
| 7 | No CSRF on financial writes | A01 | High |
| 8 | No server-side amount validation | A04 | Medium |
| 9 | Receipt IDOR | A01 | Medium |
| 10 | Missing actor in payment audit trail | A09 | Medium |
| 11 | Encoding inconsistencies | A03 | Low |
| 12 | UI-only privilege separation | A04 | Low |
| 13 | Legacy / unverified JS components | A06 | Low |