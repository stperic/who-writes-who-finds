## Review: `portal/portal_payment.php`

This PR mixes a large formatting pass with functional changes: a new recid-based audit lookup, sequence-number inserts, a new payment gateway UI, and a card-data flow change. The functional changes carry serious security and correctness risks, and some are not called out in the description. I would not merge it as is.

### Critical / High

**1. Portal patients can override `$pid` and act on other patients' invoices (authorization bypass)**
- Location: `$pid = isset($_REQUEST['pid']) ? $_REQUEST['pid'] : $pid;` and `$pid = $_REQUEST['hidden_patient_code'] > 0 ? ... : $pid;`
- In portal mode, `$pid` comes from the session, but these lines let any request parameter replace it. A logged-in portal user can post `pid` or `hidden_patient_code` for another patient, then view that patient's balances and record payments against their encounters. The `$isPortal` flag is set but never used to prevent this.
- Fix: when `$isPortal` is true, ignore request-supplied pids and use `$_SESSION['pid']` only.

**2. `recid` lookup is not scoped to the patient (IDOR)**
- Location: `$recid = (int) $_REQUEST['recid']; ... $appsql->getPortalAuditRec($recid);`
- The audit row is fetched by ID alone with no check against `$pid`. Any authenticated user, including a portal patient, can enumerate `recid` values and read other patients' stored payment records.
- Fix: query by `recid` and `pid` together, and reject rows that don't belong to the current patient.

**3. Full card numbers and CVV are stored and displayed**
- Location: the `paymentForm` fields (`cardNumber`, `cardCode`) are serialized into the AJAX body and written to `$edata['checksum']`. The audit panel then renders `$ccdata["cardNumber"]` in full for staff and `$ccdata["cardCode"]` (CVV).
- Storing CVV after authorization is prohibited by PCI DSS, even encrypted. Storing the full PAN also expands PCI scope. The staff view shows full card number and CVV.
- Fix: tokenize client-side (the AuthorizeNet branch already does this) for all gateways, never persist or transmit CVV, persist only the last four digits, and drop CVV from the audit view.

**4. Stripe secret key is emitted to every page**
- Location: `var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;`
- The `gateway_api_key` setting is described as the "API Secret" for Stripe. This is output unconditionally into the portal HTML, so any patient can read it from page source.
- Fix: emit only what each gateway needs as a publishable value. Never send a Stripe secret to the browser.

### Medium

**5. Race condition in `sequence_no` assignment**
- Location: all `SELECT IFNULL(MAX(sequence_no),0)+1 ...` followed by inserts.
- The `sqlBeginTrans()` call comes after the MAX read, so the transaction protects nothing. Two concurrent payments can get the same sequence number. The `sqlBeginTrans`/`sqlCommitTrans` pairs also have no rollback path if an insert throws.
- Fix: start the transaction before the read and use `SELECT ... FOR UPDATE`, or use a DB-side auto-increment, and roll back on failure.

**6. Inconsistent user ID for postings**
- Copay branch: `$_SESSION['authId']` is used as `post_user`, while the other branches use `$_SESSION['authUserID']`. Portal sessions may not set `authId`, which would write NULL. The original code also wrote the literal `'3'` as `post_user`, which this change silently replaces. The change should be explained or made consistent.

**7. Behavior removed without explanation**
- The `calendar_arrived($form_pid)` fallback for empty encounter IDs is removed entirely.
- The "bring today's encounter to the top" logic (`$gottoday`) is removed, so today's encounter no longer gets priority in display or the `$dispdate` override.
- These are functional changes hidden in a cleanup diff. Confirm they are intended.

**8. Unescaped output of stored card data**
- Location: `echo $ccdata["cardNumber"] . "</span><br>";` and the `cc_type`, `cardHolderName`, etc. fields use `text()`, but this one does not. Stored input could inject markup. Use `text()`.

**9. Unchecked `$_POST` and `$_REQUEST` access**
- `$_POST['form_save']`, `$_REQUEST['hidden_patient_code']`, and `$_REQUEST['radio_type_of_payment']` are read without `isset()`, producing notices under strict error reporting. `$patdata` is used without a false check.

### Low / Maintainability

**10. Malformed HTML**
- `echo '<tr height="5"><td colspan="3"></td></tr><tr">';` has a stray quote in the `<tr>` tag.
- The `$hide` logic for the copay radio button (`class="hidden"` on a `<tr>` that is never closed in the else branch) yields inconsistent markup.

**11. Dead or unused code**
- `$isPortal` is set but never read in this file.
- `flag` in the `paySubmit` handler is never set to 1, so the `if (flag)` block is dead.
- `$payrow` is referenced in the Authorized field, but its definition is outside this diff. Verify it is always set on this path.

**12. Hard-coded card years**
- The expiry dropdown is hard-coded from 2019 to 2028, and the label for 2025 was previously wrong (`2017`). Generate the list from the current year.

**13. Typos and wrong IDs**
- `comfirmation`, `payAurhorizeNet` button ID, and the `"Authorized"` label.

**14. Scope and review burden**
- The diff is roughly 600 lines, mostly whitespace and reflow. This buries the security-relevant changes. Split the reformatting into its own commit so the functional changes can be reviewed.
- The copyright year changed without a clear reason.
- The removed `$(document).ready();` and the removed `<script>` attributes are unrelated to the feature.

### Summary

The most serious issues are the session pid override (1), the unscoped `recid` lookup (2), storage and display of full PAN and CVV (3), and exposure of the Stripe secret key to the browser (4). These should be fixed before merge. The sequence-number race (5) and the removed encounter logic (7) also need attention.