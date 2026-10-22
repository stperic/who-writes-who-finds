# Security Review: `portal/portal_payment.php`

**Verdict: Do not merge.** The diff adds a new IDOR (`recid`) that exposes stored cardholder data, likely leaks the payment-gateway secret key to the browser, and keeps storing and displaying full PANs and CVVs. It also relies on pre-existing access-control gaps that let a portal patient view other patients' records and post fake payments.

---

## Critical

### 1. New IDOR via `recid` exposes any patient's stored card data
- **Location:** `$recid = (int) $_REQUEST['recid']` → `$edata = $appsql->getPortalAuditRec($recid);` → `decryptStandard($edata['checksum'])`
- **Category:** A01 Broken Access Control
- **Problem:** Any logged-in portal patient can request `portal_payment.php?recid=N`. The code loads that audit record with no check that it belongs to `$_SESSION['pid']`. It then decrypts and renders the card data stored in it.
  - The page shows the full card number whenever `transId` is set. It also shows the card holder name, zip, expiry and CVV for pending records.
  - Record IDs are sequential integers, so an attacker can walk through all of them.
- **Fix:**
  - For portal sessions, ignore `recid`, or verify `edata['patient_id'] == $_SESSION['pid']`.
  - Allow `recid` only for authorized staff with ACL `acct/bill`.

### 2. Gateway secret key exposed to the browser
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **Category:** A02 Cryptographic Failures / A05 Security Misconfiguration
- **Problem:**
  - This line runs for every gateway, including InHouse and Stripe, and for every portal user.
  - In OpenEMR, `gateway_api_key` is the "API Login Auth Name **or Secret**". With Stripe it holds the **secret key**.
  - A leaked secret key gives full control of the merchant account: charges, refunds and reading customer data.
  - For Authorize.Net, the API Login ID is meant to be used client-side and is acceptable. Even so, it should be emitted only in that branch.
- **Fix:**
  - Emit only `gateway_public_key` (the Stripe publishable key or the Authorize.Net client key) to the client.
  - Emit the login ID only inside the `AuthorizeNet` block.
  - Never emit Stripe secrets.
  - Rotate any Stripe secret key that may already have been exposed.

### 3. Patient ID taken from the request lets portal users view other patients (pre-existing, relied on)
- **Location:**
  ```php
  $pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
  $pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
  ```
- **Category:** A01 Broken Access Control
- **Problem:**
  - For portal sessions, `$_SESSION['pid']` is overridden by user input.
  - A patient can therefore view any other patient's name, PID, postal code, encounters, reasons for visit, charges, insurance and copay data. This is a PHI breach.
  - The pending-payment record is also loaded through `getPortalAudit($pid, ...)`, so other patients' card data is exposed through this path too.
  - The new query additionally pulls `postal_code` and pre-fills it into the form.
- **Fix:** When `$isPortal` is true, force `$pid = $_SESSION['pid']` and ignore request parameters. The new `$isPortal` flag is set but never used for this purpose.

### 4. Portal users can post payments and close encounters (pre-existing, relied on)
- **Location:** the `if ($_POST['form_save']) { ... }` block
- **Category:** A01 Broken Access Control / A04 Insecure Design
- **Problem:**
  - The "Post Payment" button is hidden from patients only in the UI. The server never checks for `$_SESSION['authUserID']` or an accounting ACL.
  - A portal patient can POST `form_save` with arbitrary `form_pid`, `form_upay[enc]`, `radio_type_of_payment=cash|copay|pre_payment`, `form_method` and `form_source`. Doing so:
    - inserts `ar_session` / `ar_activity` / `payments` rows, i.e., fake payments that zero out balances, for any patient;
    - for `cash`, sets `form_encounter.last_level_closed=4` and `billing.billed=1`, tampering with the billing workflow.
  - The new inserts write `$_SESSION['authUserID']`, which is empty for portal users. This makes the forged entries untraceable.
- **Fix:** Require an authenticated staff session plus `AclMain::aclCheckCore('acct','bill')` before processing `form_save`. Reject the request when `$isPortal` is true.

---

## High

### 5. Full PAN and CVV are stored and displayed (PCI DSS violation)
- **Location:**
  - `ccdata` decrypted from `checksum`
  - `echo $ccdata["cardNumber"]` for staff, or for anyone when `transId` is set
  - `<span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?>`
  - The InHouse `paySubmit` flow posts raw `cardNumber` / `cardCode` to `paylib.php`
- **Category:** A02 Cryptographic Failures / A04 Insecure Design
- **Problem:**
  - CVV must never be stored after authorization. The full PAN should never be displayed.
  - Encrypting with `encryptStandard` does not fix this. The key sits on the same server, and finding #1 provides a path to decrypt and display the data.
  - The new logic *expands* full-PAN display to patients when `transId` exists.
- **Fix:**
  - Always mask to the last 4 digits.
  - Never persist or render CVV.
  - Deprecate the InHouse mode, or at minimum strip PAN and CVV after manual processing.
  - Use tokenization only, as the Authorize.Net and Stripe paths do.

### 6. Stored XSS through unescaped card number
- **Location:** `echo $ccdata["cardNumber"] . "</span><br>";`
- **Category:** A03 Injection (XSS)
- **Problem:**
  - `cardNumber` is attacker-controlled. The HTML `pattern`/`maxlength` attributes are client-side only, and the InHouse flow posts the value directly.
  - It is rendered raw in the staff "Audit Payment" view, which leads to script execution in a billing user's session.
  - Every other field in this panel was changed to use `text()`; this one was missed.
- **Fix:** `echo text($ccdata["cardNumber"])`, together with masking per #5.

### 7. No CSRF protection on payment state changes (pre-existing)
- **Location:**
  - The `invoiceForm` POST to `portal_payment.php` (`form_save`)
  - The `paymentForm` and `payment-form` POSTs to `lib/paylib.php`
- **Category:** A01 Broken Access Control (CSRF)
- **Problem:** There is no CSRF token. A malicious page can cause a logged-in staff user to post payments or close encounters, or cause a patient to submit payment records.
- **Fix:** Add `CsrfUtils::collectCsrfToken()` hidden fields and verify them server-side in both endpoints.

---

## Medium

### 8. Client-controlled payment amount and invoice data
- **Location:**
  - `paymentAmount` is filled from `form_paytotal`
  - `invValues` is `JSON.stringify(getFormObj('invoiceForm'))` and is sent to `paylib.php`
- **Category:** A08 Software and Data Integrity Failures
- **Problem:** The amount charged and the per-encounter allocations come from the browser. `paylib.php` must recompute them server-side against the session patient's actual balances. Otherwise patients can allocate payments to arbitrary encounters or PIDs, or to mismatched amounts.
- **Fix:**
  - Recompute the totals server-side.
  - Bind the charge to `$_SESSION['pid']`.
  - Validate that the encounter IDs belong to that patient.

### 9. Receipt view relies on request-supplied patient ID (pre-existing)
- **Location:** the `$_REQUEST['receipt']` branch, which uses `form_pid` / `$pid` from the request
- **Category:** A01 Broken Access Control
- **Problem:** A portal user can view other patients' payment receipts, an IDOR with the same root cause as #3.
- **Fix:** Apply the same fix as #3.

---

## Low

### 10. Insufficient audit trail
- **Category:** A09 Security Logging and Monitoring Failures
- **Problem:**
  - Card-data views (new `recid` access, staff full-PAN display) are not logged.
  - Payment postings record an empty `user_id`/`post_user` for portal sessions.
  - `sqlQueryNoLog` is used on this financial page.
- **Fix:**
  - Log access to payment and audit records with the actor.
  - Reject postings that have no identified staff user.

### 11. Inconsistent output encoding
- **Category:** A03 Injection
- **Problem:**
  - `xlt()` (HTML encoding) is used inside JS strings, e.g., the `prompt(...)` in `getAuth()`.
  - `addslashes(xl(...))` is used inside JS.
  - `xlt()` is used inside the `form_save` attribute value.
  - `$GLOBALS['webroot']` / `assets_static_relative` are echoed raw.
  - These values are admin- or translation-controlled, so the risk is low.
- **Fix:** Use `js_escape()` for JS contexts and `attr()` for attributes.

### 12. Non-atomic sequence number generation
- **Category:** A04 Insecure Design (integrity)
- **Problem:** `SELECT MAX(sequence_no)+1` inside a transaction without `FOR UPDATE` can produce duplicate or conflicting sequence numbers when payments post concurrently.
- **Fix:** Use `SELECT ... FOR UPDATE` or a DB-level unique key with retry.

### 13. Components
- **Category:** A06 Vulnerable and Outdated Components
- **Notes:**
  - Moving off jQuery 1.11.3 is a positive change.
  - `jquery-creditcardvalidator` is unmaintained.
  - Accept.js and Stripe.js must be loaded only from the official vendor domains (their inclusion is not shown in this diff).

---

## Summary

| # | Issue | Severity | New / Pre-existing |
|---|---|---|---|
| 1 | `recid` IDOR exposes decrypted card data | Critical | New |
| 2 | `gateway_api_key` (Stripe secret) sent to client | Critical | New |
| 3 | Patient ID from request lets portal users view other patients' PHI | Critical | Pre-existing (relied on) |
| 4 | Portal users can post payments and close encounters | Critical | Pre-existing (extended) |
| 5 | PAN/CVV stored and displayed | High | Pre-existing, expanded |
| 6 | Stored XSS via `cardNumber` | High | Pre-existing, retained |
| 7 | No CSRF protection | High | Pre-existing |
| 8 | Client-controlled amount and invoice data | Medium | New flow |
| 9 | Receipt IDOR | Medium | Pre-existing |
| 10 | Logging gaps | Low | Mixed |
| 11 | Encoding inconsistencies | Low | Mixed |
| 12 | Sequence number race | Low | New |
| 13 | Components | Low | Mixed |

At minimum, fix #1–#7 before merging.