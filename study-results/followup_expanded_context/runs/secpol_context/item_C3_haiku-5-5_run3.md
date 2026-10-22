# Security Review: `portal/portal_payment.php` (plus `library/globals.inc.php` context)

**Verdict: Do not merge.** The change contains critical access-control and secret-exposure problems, and it expands handling of raw card data in ways that conflict with PCI DSS.

Several helpers this code depends on (`getPortalAuditRec`, `decryptStandard`, `paylib.php`, the receipt lookup behind `$_REQUEST['receipt']`) are not in the diff. Findings that depend on them are marked as such.

---

## Critical

### 1. Portal patients can override their session patient ID (broken access control / IDOR)
- **Location:** `portal_payment.php`, near the top of the request handling: `$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;` and `$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;`. The `$_POST['form_pid']` value is also trusted when saving.
- **OWASP:** A01 Broken Access Control
- **Problem:** The portal branch sets `$pid` from the session, but any request parameter then overwrites it. A logged-in portal patient can send `pid` or `hidden_patient_code` for another patient. The page then reads that patient's invoices and card data, and the save path records payments and `ar_activity` rows against that patient. The new `$isPortal` flag is set but never checked, so the intended restriction is not enforced.
- **Fix:** When `$isPortal` is true, ignore request-supplied `pid`, `hidden_patient_code`, and `form_pid`, and use only `$_SESSION['pid']`. Reject any mismatch.
- **Severity:** Critical

### 2. Direct object reference via `recid` (broken access control / IDOR)
- **Location:** `$recid = (int) $_REQUEST['recid']; ... $edata = $appsql->getPortalAuditRec($recid);`
- **OWASP:** A01 Broken Access Control
- **Problem:** The record is loaded by ID with no ownership check. Sequential IDs let any user, including a portal patient, load another patient's pending payment audit record. That record contains decrypted card data (see finding 5). This path bypasses the `$pid` scoping used by `getPortalAuditPec`'s replacement, `getPortalAudit($pid, ...)`.
- **Fix:** Constrain the lookup to the current patient (`WHERE id = ? AND pid = ?`) and to the authorized staff context. Confirm `getPortalAuditRec` does this. It is not in the diff.
- **Severity:** Critical

### 3. Gateway secret key is sent to every browser (cryptographic failure / security misconfiguration)
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;` and `var publicKey = ...`. The related `globals.inc.php` entry describes `gateway_api_key` as "Gateway API Login Auth Name or Secret ... API Secret for Stripe."
- **OWASP:** A02 Cryptographic Failures, A05 Security Misconfiguration
- **Problem:** The value is emitted into the HTML for every visitor, including unauthenticated patients. With Stripe selected, this leaks the **secret** key, which allows anyone to issue charges and refunds. The value is decrypted before output. Even for Authorize.Net, emitting the login ID to all clients needs careful review.
- **Fix:** Emit only the publishable key (`gateway_public_key`) to the client. Never emit secret keys or transaction keys. Make all charge operations server-side only.
- **Severity:** Critical (Stripe secret key exposure)

---

## High

### 4. Stored XSS through unescaped card number (injection)
- **Location:** Authorized-staff branch of the card display: `echo $ccdata["cardNumber"] . "</span><br>";`
- **OWASP:** A03 Injection (XSS)
- **Problem:** `cardNumber` comes from patient input in the portal form, is stored, and is later echoed without `text()` or `attr()`. A patient can enter a payload such as `<img src=x onerror=...>` in the card number field. When staff open the page, the script runs in the staff session. The other branches of the same block are escaped, so this one was missed.
- **Fix:** `echo text($ccdata["cardNumber"])`. Validate card numbers to digits server-side before storage.
- **Severity:** High

### 5. Raw card data and CVV are stored and displayed (cryptographic failure / PCI DSS violation)
- **Location:** `$ccdata = json_decode(decryptStandard($edata['checksum']), true);` and the display block that outputs `cardNumber`, `month`/`year`, and `cardCode`. Also the InHouse form that posts `cardNumber` and `cardCode` to the server, and `$('#invoiceForm')...serialize() + extra` sending `extra_values`.
- **OWASP:** A02 Cryptographic Failures
- **Problem:**
  - The full PAN is displayed unmasked to staff (`isset($_SESSION['authUserID']) || ...`).
  - The CVV (`cardCode`) is stored and rendered (`id="cvvpin"`). PCI DSS prohibits storing CVV after authorization, and this display is not restricted to staff, so it also appears to patients.
  - Card data is stored in the `checksum` column, which is not an encryption field, and that data is reversed with `decryptStandard`. Integrity is not verified.
  - The InHouse path posts raw PAN and CVV to the application server.
- **Fix:** Do not persist CVV at all. Tokenize with the gateway and store only the token and last four digits. Mask the PAN everywhere. Store encrypted data in a dedicated field with authenticated encryption (for example, AES-GCM with an integrity tag). Remove the card display for patients.
- **Severity:** High

### 6. No CSRF protection on payment state changes (broken access control)
- **Location:** The `$_POST['form_save']` handler, which inserts `ar_session`, `ar_activity`, and `payments` rows, and the `paySubmit` / `invoiceForm` AJAX posts.
- **OWASP:** A01 Broken Access Control
- **Problem:** No anti-CSRF token is checked. A malicious site can make a logged-in staff member or patient submit a payment, or post a pre-payment.
- **Fix:** Use the project's CSRF token mechanism on every state-changing POST, and verify it server-side.
- **Severity:** High

### 7. Unvalidated and unwhitelisted payment inputs (injection / insecure design)
- **Location:**
  - `$_REQUEST['radio_type_of_payment']` is compared but never whitelisted.
  - `$_REQUEST['form_prepayment']` is inserted into `ar_session` and `frontPayment` without numeric validation.
  - `$_POST['form_upay']` values are cast with `0 + $payment`, so negative values pass server-side.
  - `$form_source` / `form_method` are not whitelisted.
- **OWASP:** A04 Insecure Design, A03 Injection (data integrity)
- **Problem:** The client-side `validate()` is the only check on negative payments and overpayments. A crafted request can post negative amounts (effectively fake refunds or balance manipulation) or non-numeric values. Values are parameterized, so this is not SQL injection, but the financial data integrity is weak.
- **Fix:** Validate on the server: amounts must be positive decimals not exceeding the balance, `radio_type_of_payment` must be in an allowlist, and `form_method` must match configured `list_options`.
- **Severity:** High

---

## Medium

### 8. Race condition in `sequence_no` generation (software and data integrity)
- **Location:** Multiple blocks: `SELECT IFNULL(MAX(sequence_no),0) + 1 ... ` followed by `INSERT`, wrapped in `sqlBeginTrans()`/`sqlCommitTrans()`.
- **OWASP:** A08 Software and Data Integrity Failures
- **Problem:** The `MAX()+1` read is not locked (no `FOR UPDATE`, no unique constraint). Concurrent payments can produce duplicate `(pid, encounter, sequence_no)` values and corrupt the audit trail.
- **Fix:** Add a unique key on `(pid, encounter, sequence_no)` and use `SELECT ... FOR UPDATE`, or use an auto-increment column.
- **Severity:** Medium

### 9. Inconsistent user attribution in the audit trail (logging and monitoring failures)
- **Location:** `post_user` is set to `$_SESSION['authId']` in the copay path but to `$_SESSION['authUserID']` in the other paths. `$_SESSION['authId']` is not set in the portal context.
- **OWASP:** A09 Security Logging and Monitoring Failures
- **Problem:** Payments may be recorded with a null or wrong user, so the actor cannot be attributed. No audit log entries (`audit_events_*`) are written for payment posting or for viewing card data.
- **Fix:** Use one session key consistently, and write an audit event for each payment posting and each card-data view.
- **Severity:** Medium

### 10. Hardcoded default credential and plaintext secrets in config (security misconfiguration)
- **Location (`globals.inc.php`):**
  - `weno_account_pass` default `'7C84773D5063B20BC9E41636A091C6F17E9C1E34'` is a shipped default credential. `weno_account_id` and `weno_provider_id` also have shipped defaults.
  - `gbl_portal_cms_password`, `SMS_GATEWAY_PASSWORD`, `phone_gateway_password`, and `couchdb_pass` are typed `'text'` and stored in plaintext. They should use the `'encrypted'` or `'pwd'` type.
- **OWASP:** A05 Security Misconfiguration, A07 Identification and Authentication Failures, A02 Cryptographic Failures
- **Fix:** Remove shipped credential defaults. Change credential-type settings to `encrypted`.
- **Severity:** Medium

### 11. Weak authentication defaults (identification and authentication failures)
- **Location (`globals.inc.php`, Security tab):** `secure_password` default `'0'`, `password_history` default `'0'`, `password_compatibility` (permit unsalted passwords) default `'1'`, `password_expiration_days` default `'0'`, `secure_upload` default `'0'`.
- **OWASP:** A07, A05
- **Problem:** Strong passwords are not enforced by default, and legacy unsalted password verification is enabled.
- **Fix:** Default strong passwords and salted-only verification to on for new installs, and disable unsalted verification after migration.
- **Severity:** Medium

### 12. Pre-payment and copay authorization values are displayed in attributes and scripts without full escaping (output encoding)
- **Location:** `value='<?php echo attr($payrow['source']) ?>'` is correct, but `ccerr` is emitted through `json_encode`, and several `xl()` strings are placed inside JavaScript `alert("...")` through `addslashes`. `addslashes` is not sufficient JavaScript-context encoding.
- **OWASP:** A03 Injection (XSS)
- **Severity:** Low to Medium (translated strings are mostly trusted, but the pattern is fragile).

---

## Low

### 13. Use of an outdated front-end library is removed, but a replacement is unverified (vulnerable components)
- **Location:** `jquery-1-11-3` was replaced with `jquery/dist/jquery.min.js`. The path must exist, and its version should be confirmed. `jquery-creditcardvalidator` remains and is also unmaintained.
- **OWASP:** A06 Vulnerable and Outdated Components
- **Severity:** Low (verify the version)

### 14. External scripts loaded without Subresource Integrity (software integrity)
- **Location:** Gateway SDK scripts (Accept.js, Stripe.js) are not shown in this diff, and the local `jquery-creditcardvalidator` and `textformat.js` are included without SRI.
- **OWASP:** A08
- **Severity:** Low

### 15. Malformed HTML and dead code (quality, minor)
- **Location:** `echo '<tr class="hidden">';` and `echo '<tr">';` (malformed attribute); `$isPortal` assigned but unused; `<htlm>` typo in receipt output. These are not exploitable alone, but the unused `$isPortal` indicates the authorization check from finding 1 was intended and never implemented.
- **Severity:** Low

---

## Unverified (outside the diff; must be reviewed before merge)

- **`paylib.php`:** Must validate the amount against the invoice server-side, re-fetch invoice totals instead of trusting `inv_values`, verify the gateway response, and reject overpayments. The `inv_values` JSON is client-supplied.
- **`getPortalAuditRec` and `decryptStandard`:** Confirm the ownership constraint (finding 2) and the decryption key handling.
- **Receipt path (`$_REQUEST['receipt']`):** The lookup code that populates `$payrow` is not shown. If it is keyed by an unauthenticated ID, it is an IDOR.
- **`notifyPatient` JavaScript:** The function is referenced but not shown.

---

## Summary

| # | Finding | OWASP | Severity |
|---|---|---|---|
| 1 | Portal `pid` override via request parameters | A01 | Critical |
| 2 | `recid` IDOR on audit records | A01 | Critical |
| 3 | `gateway_api_key` (Stripe secret) emitted to browser | A02 / A05 | Critical |
| 4 | Stored XSS via unescaped `cardNumber` | A03 | High |
| 5 | Full PAN and CVV stored and displayed | A02 | High |
| 6 | No CSRF tokens on payment POSTs | A01 | High |
| 7 | Unvalidated payment amounts and enums | A04 / A08 | High |
| 8 | `sequence_no` race condition | A08 | Medium |
| 9 | Inconsistent `post_user` and missing payment audit logs | A09 | Medium |
| 10 | Hardcoded and plaintext credentials in config | A05 / A07 / A02 | Medium |
| 11 | Weak authentication defaults | A07 / A05 | Medium |
| 12 | Output-encoding fragility in JS contexts | A03 | Low–Medium |
| 13 | jQuery replacement version unverified | A06 | Low |
| 14 | No SRI on external and local scripts | A08 | Low |
| 15 | Dead code and malformed HTML | — | Low |

**Recommended actions before merge:** fix findings 1 through 3 and 4, remove CVV storage (5), add CSRF protection (6), and add server-side payment validation (7). Then review the unverified helpers.