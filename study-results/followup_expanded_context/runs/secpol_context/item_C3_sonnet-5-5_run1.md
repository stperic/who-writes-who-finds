# Security review of `portal/portal_payment.php`

I found several serious issues. The most important are the exposed gateway secret, the missing authorization on the payment-posting path, and the IDOR on the new `recid` parameter.

## Critical / High

### 1. Gateway API key (possibly the Stripe secret) sent to every portal user
- **Location:** the new `<script>` block: `var publicKey = json_encode($GLOBALS['gateway_public_key']); var apiKey = json_encode($GLOBALS['gateway_api_key']);`
- **OWASP:** A02 Cryptographic Failures / A05 Security Misconfiguration
- **Problem:** `gateway_api_key` is described in `globals.inc.php` as "Auth Name for Authorize.Net and **API Secret for Stripe**". The page emits it into client-side JavaScript for every gateway and every portal visitor. With Stripe, any logged-in patient can pull the secret key from page source and issue charges, refunds or customer lookups against the practice's account. Only the Authorize.Net path needs this value in the browser, and only the login ID is meant to be public there.
- **Fix:** Only emit `apiKey` when the gateway is `AuthorizeNet`. Never expose the Stripe secret or the transaction key to the client.
- **Severity:** Critical

### 2. IDOR: the new `recid` parameter loads any patient's payment audit record
- **Location:** `$recid = (int) $_REQUEST['recid']; ... $appsql->getPortalAuditRec($recid);`
- **OWASP:** A01 Broken Access Control
- **Problem:** The record is fetched by ID alone, with no check that it belongs to the session patient (`$_SESSION['pid']`). The record's encrypted `checksum` is then decrypted and rendered. A portal user can enumerate `recid` values and read other patients' cardholder name, zip, card number and CVV, as well as invoice data. When `transId` is present, the full card number is shown even to non-staff (see #4).
- **Fix:** Require `$edata['pid'] == $_SESSION['pid']` for portal users. Allow `recid` only for authenticated staff, and ideally only for staff with billing ACL.
- **Severity:** Critical

### 3. Patient ID taken from the request, and payment posting has no authorization
- **Location:**
  - `$pid = $_REQUEST['pid'] ?? $pid; $pid = $_REQUEST['hidden_patient_code'] > 0 ? ... : $pid;`
  - `$form_pid = $_POST['form_pid']`
  - the `if ($_POST['form_save'])` block
- **OWASP:** A01 Broken Access Control / A04 Insecure Design
- **Problem (pid override):** Any portal session can override `pid` and `form_pid` and view or act on other patients' invoices and payment data.
- **Problem (unauthenticated posting):** The `form_save` branch performs no check that the caller is staff, and none that a payment actually cleared. A portal patient can POST `form_save=1&form_upay[enc]=amount&radio_type_of_payment=cash` and write `ar_session` and `ar_activity` rows. For `cash`, this also sets `form_encounter.last_level_closed=4` and `billing.billed=1`. The invoice is thereby marked paid without any money changing hands, and the paid amounts are attributed to a null or other user.
- **Problem (amounts):** Amounts are not validated server-side. `$amount = 0 + $payment` accepts negative values, and `form_prepayment` is unchecked. Validation exists only in JavaScript.
- **Fix:** Always derive `pid` from the session for portal users. Gate the posting branch on a staff session (`authUserID`) plus the billing ACL. Validate amounts server-side (numeric, positive, not more than the balance) and check that the encounter belongs to the patient.
- **Severity:** High

### 4. Stored XSS: unescaped card number output
- **Location:** `echo $ccdata["cardNumber"] . "</span><br>";`, in the branch `isset($_SESSION['authUserID']) || isset($ccdata["transId"])`
- **OWASP:** A03 Injection (XSS)
- **Problem:** The other fields were switched to `text()`, but this one is echoed raw. `cardNumber` is attacker-controlled. Client-side validation is trivially bypassed by posting directly to `paylib.php`, and the value is stored encrypted in the audit table. When staff open the pending payment, the payload runs in their authenticated OpenEMR session, which can lead to privilege escalation or theft of PHI.
- **Fix:** Use `text()`.
- **Severity:** High

### 5. Full PAN and CVV stored and displayed
- **Location:** the display block (`cardNumber`, `cardCode`) and the in-house gateway flow
- **OWASP:** A02 Cryptographic Failures / A04 Insecure Design
- **Problem:** In-house mode stores the full card number and CVV (encrypted with `decryptStandard`) and later renders them in clear text. PCI DSS forbids storing the CVV after authorization. Displaying the full PAN to anyone with `authUserID` or `transId` (including portal users) is also a leak. The `transId` branch shows the full number even though the card has already been charged.
- **Fix:** Never persist the CVV. Mask the PAN everywhere except the minimum staff need. Prefer tokenized gateways, and consider removing in-house mode.
- **Severity:** High

## Medium

### 6. Client-controlled charge amount and invoice data
- **Location:** hidden inputs `payment` (`#paymentAmount`) and `invValues`, populated by JavaScript from `form_paytotal`
- **OWASP:** A04 Insecure Design / A08 Data Integrity Failures
- **Problem:** The amount sent to Authorize.Net or Stripe via `paylib.php` comes from the browser. `paylib.php` is not in this diff and must be checked, but it must recompute the amount from server-side balances. A user could underpay, or submit negative or zero amounts.
- **Severity:** Medium

### 7. No CSRF protection
- **Location:** `invoiceForm`, `paymentForm`, `payment-form` and the AJAX posts to `paylib.php`
- **OWASP:** A01 / A04
- **Problem:** The state-changing payment-posting form has no CSRF token. A staff session visiting a hostile page could be made to post payments.
- **Severity:** Medium

### 8. Missing audit logging
- **OWASP:** A09 Logging and Monitoring Failures
- **Problem:** Viewing decrypted card data, authorizing a payment, and posting `ar_session` and `ar_activity` rows are not logged. Portal-initiated postings have a null `user_id` or `post_user`. `$_SESSION['authId']` and `authUserID` are used inconsistently, which degrades attribution.
- **Severity:** Medium

## Low

### 9. Verbose error disclosure
- **Location:** `alert(data)`, `alert(error)` and `console.log` of gateway error codes
- **OWASP:** A05
- **Problem:** Raw server and gateway error text is shown to the user and written to the console.
- **Severity:** Low

### 10. Third-party scripts and components
- **OWASP:** A06 / A08
- **Problem:** The jQuery path changed to `jquery/dist/jquery.min.js`, and the old `jquery.creditCardValidator` is still used. Stripe and Authorize.Net scripts are loaded without Subresource Integrity. Verify the jQuery version is current and patched.
- **Severity:** Low

### 11. Duplicate element IDs
- **Location:** `mode`, `cc_type`, `paymentAmount`, `invValues`, `payTotal`, `cardHolderName`
- **OWASP:** A04
- **Problem:** The same IDs appear in several forms (for example the Stripe and non-Stripe variants, plus `invoiceForm`). `$("#mode").val(...)` and `getElementById` can target the wrong element, causing unpredictable payment-mode and data handling.
- **Severity:** Low

## Positive observations
- The new `$recid` is cast to int.
- The queries shown are parameterized.
- Output of `ccdata` fields was moved to `text()` (except `cardNumber`).
- Tokenization is used for the Authorize.Net and Stripe paths.

Recommendation: do not merge until findings 1–5 are fixed.