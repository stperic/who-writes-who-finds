# Security Review: `portal/portal_payment.php`

**Verdict: Do not merge.** The diff adds payment-card handling that violates PCI DSS, and it introduces an access-control bypass that exposes other patients' card data. It also adds a stored XSS path against staff users.

Files not in the diff (`paylib.php`, `ApplicationTable::getPortalAuditRec`, `decryptStandard`, `globals.php`, and the auth check in the `else` branch) were not reviewed. Several findings depend on how they behave.

---

## Findings

### 1. CVV (card security code) is stored and displayed. CRITICAL
- **Location:** Audit payload read at `$ccdata = json_decode(decryptStandard($edata['checksum']))`. Rendered at `<span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?>`. Collected from `cardCode` in the new modal form and posted to the server.
- **OWASP:** A02 Cryptographic Failures; A04 Insecure Design.
- **Problem:** The patient's CVV2 is persisted in the audit record for pending payments and then rendered on the page. PCI DSS 3.2 §3.2 forbids storing CVV2 after authorization, even encrypted. Anyone who can view the record, including any staff user with the authorize action, sees it. The CVV is also shown to every viewer, not only staff.
- **Fix:** Do not persist `cardCode`. Tokenize the card with the gateway (Accept.js/Stripe already do this for two of the three options) and store only the token. Remove the CVV from the rendered output.

### 2. Full PAN and card data stored and displayed. CRITICAL
- **Location:** `echo $ccdata["cardNumber"]` for authorized users; `substr($ccdata["cardNumber"], -4)` otherwise. The `InHouse` gateway posts `cardNumber`, `month`, `year`, and `cardCode` in plaintext to `paylib.php`, which stores them.
- **OWASP:** A02 Cryptographic Failures.
- **Problem:** The full PAN is persisted, encrypted only with `decryptStandard`, and is decrypted and printed for staff. Storing raw PAN in the application database puts the merchant out of PCI scope and into full PCI DSS obligations. The `InHouse` option is the default path ("Send Payment").
- **Fix:** Use gateway tokenization for all options. Remove `InHouse` raw-card storage, or restrict it to the gateway's own vault. Never render the full PAN.

### 3. Insecure direct object reference via `recid`. HIGH
- **Location:** `$recid = (int) $_REQUEST['recid']; $edata = $appsql->getPortalAuditRec($recid);`
- **OWASP:** A01 Broken Access Control.
- **Problem:** When `recid` is supplied, the audit record is loaded by ID with no check that it belongs to `$pid` (the logged-in patient). A portal user can enumerate `recid` values and decrypt and view other patients' pending card data, including card numbers and names. Even with the CVV fix, this exposes other patients' payment data.
- **Fix:** Load the record only with `WHERE id = ? AND pid = ?`, bound to the session patient for portal users. Reject a mismatch.

### 4. Patient ID override allows cross-patient payment actions. HIGH
- **Location:** `$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;` and `$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;`. Then `$form_pid = $_POST['form_pid']` is used for all writes.
- **OWASP:** A01 Broken Access Control.
- **Problem:** In portal mode, `$pid` should come only from the session. Request parameters override it, so an authenticated patient can post payments, `ar_session` rows, `ar_activity` rows, and `billing` / `form_encounter` status updates against any patient. The new `$isPortal` flag is set but never used to enforce this.
- **Fix:** When `$isPortal` is true, set `$pid` from `$_SESSION['pid']` and ignore all request-supplied patient IDs. Use `$isPortal` to gate the override. Check that the encounter belongs to that patient before writing.

### 5. Stored XSS via unescaped card number. HIGH
- **Location:** `echo $ccdata["cardNumber"] . "</span><br>";` and the `substr(...)` branch, neither wrapped in `text()`/`attr()`.
- **OWASP:** A03 Injection (XSS).
- **Problem:** `cardNumber` is taken from patient input with no server-side format check. A patient can submit HTML or script in that field. When staff open the record (the "Authorize" view), the script runs in the staff session. Staff are the higher-privilege users, so this is a privilege escalation path.
- **Fix:** Escape with `text()`. Validate on the server that the card number is digits only (Luhn check optional, length 12–19 digits).

### 6. Missing server-side validation of payment amounts and method. MEDIUM
- **Location:** `if ($amount = 0 + $payment)` with `$_POST['form_upay']`; `$_REQUEST['form_prepayment']` passed unchecked into `ar_session.pay_total`; `$_REQUEST['radio_type_of_payment']` is not allow-listed.
- **OWASP:** A04 Insecure Design; A08 Software and Data Integrity Failures.
- **Problem:** The "no negative payments" and "cannot exceed balance" checks exist only in JavaScript. A crafted request can post negative amounts, amounts above the balance, arbitrary `radio_type_of_payment` values, or `enc = 0`. The `calendar_arrived()` fallback was removed, so `$enc` may be 0. Writes to `ar_activity` and `ar_session` are then unvalidated.
- **Fix:** Validate on the server: numeric, non-negative, at most the computed balance, `radio_type_of_payment` in an explicit allow-list, and `$enc` must reference a real encounter for `$pid`.

### 7. No CSRF protection on state-changing requests. MEDIUM
- **Location:** `if ($_POST['form_save'])` and the new `invoiceForm` / `paymentForm` posts to `paylib.php`.
- **OWASP:** A01 Broken Access Control.
- **Problem:** No anti-CSRF token is checked. A third-party page can cause a logged-in staff user to post payments.
- **Fix:** Add and verify a per-session CSRF token (OpenEMR's `CsrfUtils`) on every POST.

### 8. Unvalidated `sequence_no` race in ar_activity. LOW
- **Location:** `SELECT IFNULL(MAX(sequence_no),0)+1 ...` followed by `INSERT`, inside `sqlBeginTrans()`/`sqlCommitTrans()`.
- **OWASP:** A04 Insecure Design.
- **Problem:** Without a row lock or unique constraint, concurrent payments can produce duplicate sequence numbers. This is an integrity issue for accounting records.
- **Fix:** Add a UNIQUE constraint on `(pid, encounter, sequence_no)` or use `SELECT ... FOR UPDATE`.

### 9. Attacker-influenced `post_user` and `session_id` changes. LOW
- **Location:** `$_SESSION['authId']` is now used as `post_user` in the copay branch, where it was previously a constant. `$_SESSION['authUserID']` is used in the others.
- **OWASP:** A09 Logging and Monitoring Failures.
- **Problem:** In portal mode, `authId` may be unset, so audit rows record NULL or the wrong actor. This weakens attribution for financial transactions.
- **Fix:** Use one consistent identity source, and set it from the authenticated principal, not the request.

### 10. Gateway configuration exposed to the browser. LOW / INFO
- **Location:** `var publicKey = <?php echo json_encode($GLOBALS['gateway_public_key']); ?>; var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **OWASP:** A05 Security Misconfiguration.
- **Problem:** Secrets-adjacent gateway credentials are printed into every payment page, including the patient portal. Public/client keys are generally acceptable to expose, but `apiKey` (Authorize.net API login ID) should be confirmed as client-safe. Any transaction or secret key must never reach this page.
- **Fix:** Expose only the documented client-side identifiers. Confirm that no secret key is printed.

### 11. Third-party scripts loaded without integrity checks. LOW
- **Location:** `jquery/dist/jquery.min.js`, Stripe.js, and Authorize.net Accept.js (loaded by the template or gateway SDK).
- **OWASP:** A08 Software and Data Integrity Failures; A06 Vulnerable Components.
- **Problem:** Scripts run in a page that handles card data, and none has SRI. The jQuery path changed, so confirm the version is current and free of known CVEs.
- **Fix:** Pin versions, add SRI where possible, and keep jQuery current.

### 12. Pre-existing: receipt lookup by request ID. NEEDS VERIFICATION
- **Location:** `if ($_POST['form_save'] || $_REQUEST['receipt'])`, which loads `$payrow` from the `receipt` parameter (code not in the diff).
- **OWASP:** A01 Broken Access Control.
- **Problem:** If `$payrow` is loaded by ID without a `pid` check, any portal user can view other patients' receipts. Confirm and bind to `$pid`.

### 13. Information leakage through alerts and logs. LOW
- **Location:** `alert(error)` in the Stripe and AuthorizeNet handlers; `console.log` of gateway error codes and messages.
- **OWASP:** A09 Logging and Monitoring Failures.
- **Problem:** Gateway error details and raw exception text reach the user and browser console. Minor, but it aids probing.
- **Fix:** Show generic messages to users. Log detail server-side only.

---

## Summary

| # | Issue | Severity | OWASP |
|---|---|---|---|
| 1 | CVV stored and displayed | Critical | A02 |
| 2 | Full PAN stored and displayed | Critical | A02 |
| 3 | `recid` IDOR exposes other patients' card data | High | A01 |
| 4 | `pid` override allows cross-patient writes | High | A01 |
| 5 | Stored XSS via unescaped card number, against staff | High | A03 |
| 6 | Payment amounts and method not validated server-side | Medium | A04 / A08 |
| 7 | No CSRF tokens | Medium | A01 |
| 8 | `sequence_no` race | Low | A04 |
| 9 | Inconsistent `post_user` identity | Low | A09 |
| 10 | Gateway config exposed to browser | Low / Info | A05 |
| 11 | Third-party scripts without SRI | Low | A08 / A06 |
| 12 | Receipt lookup possibly unscoped (pre-existing) | Needs verification | A01 |
| 13 | Error detail leakage | Low | A09 |

**Required before merge:** items 1–5. Items 6–7 should also be addressed in this change; they are not optional for a payment flow. Item 12 needs a check of the receipt-loading code.