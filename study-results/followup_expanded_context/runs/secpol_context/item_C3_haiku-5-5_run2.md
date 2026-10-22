# Security Review: `portal/portal_payment.php` (payment/invoice flow)

**Verdict: Do not merge.** The change adds and exposes card data, leaks a payment secret to the browser, and relies on access checks that are missing or bypassable. Several findings are exploitable by an ordinary portal patient.

Line references are approximate because the diff does not carry line numbers for the new file.

---

## Critical

### 1. Patient ID can be overridden by request parameters (broken access control, IDOR)
- **Location:** `$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;` and `$pid = $_REQUEST['hidden_patient_code'] > 0 ? ... : $pid;` (unchanged context, but this code now drives the new display and save logic)
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The portal session sets `$pid = $_SESSION['pid']`, then both lines overwrite it with values from `$_REQUEST`. A logged-in portal patient can send `pid=<other patient>` and read that patient's billing data, invoices, and payment audit. The `$_REQUEST['hidden_patient_code'] > 0` check also reads an undefined index when the parameter is absent, which emits a notice.
- **Fix:** When `$isPortal` is true, ignore request-supplied `pid` values and use only `$_SESSION['pid']`. Reject any request whose `pid` does not match the session.

### 2. Payment audit record lookup by `recid` is not scoped to the patient (IDOR)
- **Location:** `$recid = (int) $_REQUEST['recid']; ... $edata = $appsql->getPortalAuditRec($recid);`
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** Any authenticated portal user can supply an arbitrary `recid`, and the code loads that audit row with no check that it belongs to the session patient. The row contains encrypted card data, which is decrypted and rendered (see Finding 3). Whether `getPortalAuditRec()` filters by pid is not shown, so this must be verified. Unless it does, this is a direct IDOR.
- **Fix:** Query by `recid AND pid = $session_pid`, or verify ownership before decrypting.

### 3. Portal users can submit payment posts for any patient (missing authorization)
- **Location:** `if ($_POST['form_save']) { ... }` block, including `pre_payment`, `copay`, `invoice_balance`, and `cash` branches
- **OWASP:** A01:2021 Broken Access Control
- **Problem:** The save block does not check `$_SESSION['authUserID']` or the portal session. It trusts `form_pid`, `form_upay[...]`, `radio_type_of_payment`, and `form_prepayment` from the request. A portal user can POST directly to this endpoint to create `ar_session` and `ar_activity` rows for other patients, mark encounters `last_level_closed=4` and `billed=1` (the `cash` branch), and post arbitrary prepayments. `$_SESSION['authId']` is also unset for portal users, so the `copay` branch inserts a null user.
- **Fix:** Gate the staff save path on `$_SESSION['authUserID']` and ACL checks. Gate the portal path on session pid only, and restrict it to the `copay`/`invoice_balance` flow that routes through `paylib.php`. Verify `$form_pid` against the authenticated context on every write. `$isPortal` is computed but never used in the shown code, which suggests this gating was intended and not implemented.

### 4. Payment gateway secret key rendered into every page (sensitive data exposure)
- **Location:** `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- **OWASP:** A02:2021 Cryptographic Failures; A05:2021 Security Misconfiguration
- **Problem:** The `gateway_api_key` setting is documented as "Auth Name for Authorize.Net and API Secret for Stripe." The line is unconditional, so with Stripe configured the Stripe secret key is embedded in the HTML of every portal payment page and is readable by any patient. Stripe secret keys grant full account access (refunds, charges, customer data).
- **Fix:** Emit only the publishable key to the browser. Send the secret key only from server-side code. For Authorize.Net, the API login ID is designed to be client-visible for Accept.js, but this should be confirmed for the chosen gateway configuration.

### 5. Card CVV is stored and redisplayed (PCI DSS violation)
- **Location:** Payment save to `$ccdata` via `paylib.php` (not in diff, but the stored data is consumed here); display: `<span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?></span>`
- **OWASP:** A02:2021 Cryptographic Failures
- **Problem:** The pending-authorization record stores the full PAN, CVV (`cardCode`), expiry, and cardholder data. PCI DSS prohibits storing CVV after authorization, and storing it at all in this form is a compliance failure. The new UI then displays the CVV to staff and the full card number to staff (Finding 6). Encrypting the blob with `decryptStandard` does not remove the violation, and the key is available to anything that can read the same config.
- **Fix:** Do not persist CVV. Tokenize through the gateway (the Authorize.Net and Stripe branches already do this; the InHouse branch should not exist for card data). Store only a token and last four digits. Remove CVV display entirely.

---

## High

### 6. Stored XSS via unescaped card number
- **Location:** `echo $ccdata["cardNumber"] . "</span><br>";` and `echo "**********  " . substr($ccdata["cardNumber"], -4) ...`
- **OWASP:** A03:2021 Injection (XSS)
- **Problem:** `cardNumber` is user-supplied and is echoed without `text()` or `htmlspecialchars()` in both branches. The client-side Luhn validator is not a server-side control. A patient can submit a card number containing HTML or script, and the script executes in the browser of any staff member who opens the audit view.
- **Fix:** Wrap in `text()`. Validate and normalize card numbers server-side (digits only) before storage.

### 7. Full card number displayed to staff
- **Location:** `if (isset($_SESSION['authUserID']) || isset($ccdata["transId"])) { echo $ccdata["cardNumber"] ...`
- **OWASP:** A02:2021 Cryptographic Failures; A01:2021 Broken Access Control
- **Problem:** Staff now see the complete PAN in the page. Combined with the CVV display, a staff member (or anyone with access to an unlocked browser session) can capture full card data. The previous code masked to the last four digits for everyone.
- **Fix:** Show only the last four digits to all users. Reveal nothing further in the browser.

### 8. No CSRF protection on payment-changing endpoints
- **Location:** `<form id="invoiceForm" method='post' ...>`; `$_POST['form_save']` handler; `paymentForm` posting to `paylib.php`
- **OWASP:** A01:2021 Broken Access Control; A04:2021 Insecure Design
- **Problem:** No anti-CSRF token is generated or checked. A malicious page can auto-submit a POST to `portal_payment.php` as a logged-in staff member or patient, creating payments or altering `billed` and `last_level_closed` state.
- **Fix:** Add per-session CSRF tokens to every state-changing form and validate them server-side. Enforce SameSite cookies.

### 9. Card data transmitted and stored by the server for the InHouse gateway
- **Location:** `paymentForm` (non-Stripe branch) posts `cardNumber`, `cardCode`, `month`, `year` to `./lib/paylib.php`
- **OWASP:** A02:2021 Cryptographic Failures; A04:2021 Insecure Design
- **Problem:** The default gateway (`InHouse`) collects raw PAN and CVV and sends them to the OpenEMR server, which stores them (Finding 5). This makes the application within PCI scope with no tokenization. Transport security is also not enforced in the diff.
- **Fix:** Require a tokenizing gateway for card payments. Refuse to accept raw PAN. Enforce HTTPS for the portal.

---

## Medium

### 10. Missing audit logging for sensitive operations (A09)
- **Location:** Viewing decrypted card data; `sqlBeginTrans`/`sqlInsert` payment writes; `getPortalAuditRec` lookup
- **Problem:** Viewing another record's card data, posting payments, and changing `billed` and `last_level_closed` are not logged. There is no record of who viewed or altered card and payment data.
- **Fix:** Log every card-data view, payment post, and status change with user, pid, and record ID through the existing audit logger.

### 11. Race condition in `sequence_no` generation (data integrity, A08)
- **Location:** `SELECT IFNULL(MAX(sequence_no),0) + 1 ... ` followed by `INSERT INTO ar_activity`
- **Problem:** `sqlBeginTrans()` does not lock. Two concurrent posts can read the same MAX and insert duplicate sequence numbers, which can corrupt the ledger. The `sqlBeginTrans` wrapping suggests the author expected atomicity that the query does not provide.
- **Fix:** Use `SELECT ... FOR UPDATE` on the parent rows, a unique key on `(pid, encounter, sequence_no)` with retry, or an auto-increment column.

### 12. No validation of payment amounts and types (A04)
- **Location:** `$amount = 0 + $payment;` and `$_REQUEST['form_prepayment']` passed directly to `pay_total`
- **Problem:** Negative, non-numeric, and excessive amounts are not rejected server-side. Only client-side JavaScript checks exist. `radio_type_of_payment` is an unvalidated enum taken from `$_REQUEST`.
- **Fix:** Validate amounts as positive decimals with a sane maximum. Use a strict allowlist for `radio_type_of_payment` and `form_method`.

### 13. Mixed request sources for security-relevant input (A04/A05)
- **Location:** `$_POST['form_save']`, `$_POST['form_upay']`, `$_REQUEST[...]` throughout
- **Problem:** Some values come from `$_POST` and others from `$_REQUEST`, which also accepts GET and cookies. This widens the injection surface and makes validation inconsistent.
- **Fix:** Read only from `$_POST` for state-changing actions, and validate each value.

### 14. Receipt access not verified (unconfirmed, A01)
- **Location:** `if ($_POST['form_save'] || $_REQUEST['receipt'])` and `$payrow` lookup
- **Problem:** `$_REQUEST['receipt']` selects a payment record. The lookup that populates `$payrow` is not shown. If it is keyed only by an ID, any authenticated user can view other patients' receipts.
- **Fix:** Verify that the record belongs to the authorized pid before rendering.

---

## Low / Informational

- **Unused `$isPortal` flag** (`$isPortal = true`): set but not referenced in shown code. It should drive the access gating described in Finding 3.
- **Inline JavaScript string construction:** `alert("<?php echo addslashes(xl(...)) ?>")` and `var ccerr = <?php echo json_encode(...) ?>` depend on translation strings being free of `</script>`. `json_encode` does not escape `</`. Use `JSON_HEX_TAG | JSON_HEX_APOS | JSON_HEX_QUOT | JSON_HEX_AMP` for script-context output.
- **Outdated component:** `jquery-creditcardvalidator` is an old third-party library loaded without integrity checks. Add Subresource Integrity (SRI) hashes or vendor the file. The jQuery path change to `jquery/dist/jquery.min.js` is an improvement, but confirm the bundled version has no known CVEs.
- **Sequence of `session_start()` and `session_destroy()`:** when the portal condition fails, the code destroys the session without regenerating the session ID. Session fixation is not addressed.
- **Stripe script:** `Stripe(publicKey)` is used, but the Stripe.js include is not in this diff. Confirm it loads from `https://js.stripe.com`.

---

## Pre-existing Issues in Touched Code

- The `pid` override (Finding 1) and the unvalidated `form_save` path (Finding 3) existed before this change. This diff adds new sensitive operations on top of them, so they must be fixed here.
- `decryptStandard` is used for card data, and the encryption key lifecycle is not shown. Confirm the key is not stored in the webroot.

---

## Recommended Actions (in priority order)

1. Remove CVV storage and display entirely. Tokenize all card data through the gateway, and do not offer the InHouse raw-card path.
2. Remove `apiKey` from client-side JavaScript. Emit only publishable keys to the browser.
3. Enforce session-bound patient identity: ignore request `pid` and `hidden_patient_code` for portal sessions, and scope `recid` lookups by pid.
4. Gate the staff save path on `authUserID` and the appropriate ACL. Gate the portal path to its own narrow flow.
5. Escape or mask all card output (`text()`, last-four only). Validate `cardNumber` server-side.
6. Add CSRF tokens to all payment-changing forms and endpoints.
7. Add audit logging for card-data access and payment writes.
8. Fix the `sequence_no` race with proper locking or a unique constraint.
9. Validate amounts and enum inputs server-side.

I could not review `paylib.php`, `getPortalAuditRec()`, the receipt `$payrow` query, or the ACL checks on the staff path. Those files determine whether Findings 2, 3, and 14 are exploitable as described, and they should be reviewed before this change is considered safe.