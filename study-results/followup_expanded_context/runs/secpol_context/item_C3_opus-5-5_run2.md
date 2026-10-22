# Security Review: `portal/portal_payment.php`

## Summary

This change adds Authorize.Net and Stripe integrations, plus a new `recid` lookup of payment audit records. The most serious problem is that **the gateway secret key is written into the patient-facing page**. The change also adds a new IDOR that exposes other patients' card data. Several older access-control and PCI problems remain in code this change touches.

---

## 1. Payment gateway secret key exposed to the browser (NEW)

- **Location:** the new JS block in the "Record Payment" view:
  ```php
  var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>;
  var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
  ```
- **OWASP category:** A02 Cryptographic Failures (sensitive data exposure). Also A05 Security Misconfiguration.
- **Problem:**
  - `library/globals.inc.php` defines `gateway_api_key` as *"The Auth Name or API key for selected account. Auth Name for Authorize.Net and **API Secret for Stripe**"*. It is stored as an `encrypted` global, which marks it as a secret.
  - This page prints it unconditionally into every page load, including for unauthenticated-to-staff portal patients.
  - The Stripe path only ever uses `publicKey` (`Stripe(publicKey)`). So `apiKey` is emitted for nothing when Stripe is selected, and that is exactly the case where it holds the Stripe secret key (`sk_live_…`).
  - Anyone with portal access, or anyone who can view the page source, cached HTML or proxy logs, gets the practice's full Stripe secret. With it they can issue refunds and payouts, read customer and charge data, and create charges.
  - For Authorize.Net, the API Login ID is less sensitive, since Accept.js expects it client-side. It should still only be emitted when that gateway is active.
- **Severity:** **Critical**
- **Fix:**
  - Never send `gateway_api_key` or `gateway_transaction_key` to the client.
  - Emit `apiKey` only inside the `AuthorizeNet` branch, and only the API Login ID.
  - Rename or split the setting so that a Stripe secret can never be in that field.
  - Rotate any Stripe secret key that has been deployed with this code.

## 2. IDOR via new `recid` parameter exposes other patients' card data (NEW)

- **Location:**
  ```php
  $recid = isset($_REQUEST['recid']) ? (int) $_REQUEST['recid'] : 0;
  ...
  if ($recid) { $edata = $appsql->getPortalAuditRec($recid); }
  ...
  $ccdata = json_decode(decryptStandard($edata['checksum']), true);
  ```
- **OWASP category:** A01 Broken Access Control
- **Problem:**
  - A portal patient can enumerate `recid=1,2,3…`.
  - Nothing checks that the audit record belongs to `$_SESSION['pid']`, or that the caller is staff.
  - The record is decrypted and rendered: cardholder name, zip, card number, expiry, CVV, transaction ID and auth code.
  - The card number is shown unmasked when `transId` is set (see #4).
- **Severity:** **Critical**
- **Fix:**
  - Honour `recid` only for authenticated staff (`$_SESSION['authUserID']` plus an ACL check).
  - Otherwise, verify that `$edata['patient_id'] == $_SESSION['pid']`.

## 3. Portal patient can override `pid` and act on any patient (pre-existing, relied upon)

- **Location:**
  ```php
  $pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;
  $pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;
  ```
  The `form_save` handler also uses `$_POST['form_pid']`.
- **OWASP category:** A01 Broken Access Control
- **Problem:**
  - The session-bound `pid` set for portal users is overwritten by request input.
  - A portal patient can view another patient's name, postal code, encounters, balances, insurance and pending card data.
  - They can also post payments and ledger entries against another patient.
  - The new code relies on `$pid` for `getPortalAudit`, `$patdata` (now including `postal_code`), and the pre-filled card-holder name and zip.
- **Severity:** **High**
- **Fix:** when `$isPortal` is true, force `$pid = $_SESSION['pid']` and ignore `pid`, `hidden_patient_code` and `form_pid`.

## 4. Full PAN and CVV stored and displayed (PCI violation, worsened)

- **Location:** the `panel-body` output.
  - `echo $ccdata["cardNumber"]` is unescaped, and is shown unmasked when `isset($_SESSION['authUserID']) || isset($ccdata["transId"])`. The new `transId` condition reveals the full PAN to the patient too.
  - `text($ccdata["cardCode"])` displays the CVV.
- **OWASP category:** A02 Cryptographic Failures, A04 Insecure Design
- **Problem:**
  - Storing CVV after authorization is prohibited by PCI DSS 3.2.
  - The full PAN is shown to staff and now to patients.
  - The "InHouse" flow still posts the raw PAN and CVV to `paylib.php`.
  - The card number is also echoed without `text()`, which allows stored XSS through a crafted `cardNumber`.
- **Severity:** **High**
- **Fix:**
  - Never persist CVV.
  - Store only a token and the last 4 digits.
  - Always mask the PAN.
  - Escape all output with `text()`.

## 5. Payment posting has no server-side authorization or CSRF protection (pre-existing, touched)

- **Location:** the `if ($_POST['form_save'])` block.
- **OWASP category:** A01 Broken Access Control; A04 Insecure Design (no CSRF tokens)
- **Problem:**
  - The "Post Payment" button is hidden from portal users, but the handler never checks `authUserID` or ACLs.
  - A portal session can POST `form_save` with `radio_type_of_payment=cash`. That inserts `ar_session`/`ar_activity` payments and runs `update billing set billed=1` / `form_encounter last_level_closed=4`, which marks encounters as paid or closed without any money changing hands.
  - Amounts (`form_upay`, `form_prepayment`) are client-controlled. Negative amounts are only rejected in JavaScript.
  - In portal context `$_SESSION['authUserID']` and `authId` are null, so ledger entries have no accountable user (A09 logging failure).
  - There is no CSRF token on this form or on the `paylib.php` submissions.
- **Severity:** **High**
- **Fix:**
  - Require an authenticated staff user with billing ACL for `form_save`.
  - Validate amounts server-side as positive numerics.
  - Add CSRF tokens.

## 6. Minor issues

- **Unescaped outputs (A03 Injection/XSS, low):**
  - `value='<?php echo xlt('Invoice'); ?>'` uses the wrong escaper for an attribute context.
  - `getAuth()` puts `xlt()` output inside a JS string; it should use `xlj`/`json_encode`.
  - `$GLOBALS['assets_static_relative']` and `webroot` are echoed raw.
- **Third-party scripts (A08):** the Stripe.js and Accept.js usage assumes externally loaded scripts. Ensure they come from the official HTTPS origins; SRI cannot be used for Stripe.js, so pin origins via CSP.
- **Error leakage:** `alert(data)` displays raw server responses to the user. Make sure `paylib.php` does not return gateway or debug details.

---

**Recommendation:** Do not merge until #1 and #2 are fixed. Rotate any exposed Stripe secret key. Address #3–#5 in the same release, since the new gateway code depends on these flawed paths.