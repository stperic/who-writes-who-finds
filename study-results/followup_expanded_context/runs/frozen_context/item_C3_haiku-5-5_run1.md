## Review: portal payment page rewrite (`portal/portal_payment.php`)

This PR mixes a large set of cosmetic reformatting with real behavior changes, and it introduces a card-data handling problem. I would not merge it as-is.

### Critical

**1. Card verification code (CVV) is stored and displayed (PCI DSS violation).**
Location: the `ccdata` display block (`echo text($ccdata["cardCode"])`, `id="cvvpin"`), and the form field `cardCode` submitted through `invoiceForm`/`paymentForm`.
The CVV is persisted in the audit record and shown to staff. Card data must not be retained after authorization, and CVV in particular must never be stored. The full PAN is also written into the audit row (`cardNumber`), and staff see it unmasked (`echo $ccdata["cardNumber"]` when `authUserID` is set). Storage should be limited to a token or last-4, and the CVV should be dropped from the client payload entirely.

**2. Missing authorization on patient identity (IDOR and cross-patient posting).**
Location: `$pid = $_REQUEST['hidden_patient_code'] > 0 ? ... : $pid;`, `$form_pid = $_POST['form_pid'];`, and `$recid = (int) $_REQUEST['recid']; $appsql->getPortalAuditRec($recid);`.
In portal mode, `$pid` comes from the session, but the save path then takes `form_pid` and `hidden_patient_code` from the request. A logged-in patient can alter these to post payments to `ar_session`/`ar_activity` for another patient, or to read another patient's audit record via `recid`. `getPortalAuditRec` should be checked to confirm it filters by pid, and in portal mode every request-supplied pid should be verified equal to `$_SESSION['pid']`.

### High

**3. Encounter fallback removed, so payments can post to encounter 0.**
The removed block `if (!$enc) { $enc = calendar_arrived($form_pid); }` was the only path that resolved a missing encounter. Without it, `$enc` can be 0 and `ar_activity` rows and `frontPayment` calls are written against no encounter. Either restore the logic or explicitly reject `$enc == 0`.

**4. Race condition in sequence number allocation.**
Location: the four `SELECT IFNULL(MAX(sequence_no),0)+1 ... ` calls followed by `INSERT`.
Wrapping the read in `sqlBeginTrans()`/`sqlCommitTrans()` does not prevent two concurrent requests from reading the same MAX under default InnoDB isolation, since a plain SELECT takes no lock. Two rows for the same encounter can get the same `sequence_no`. Use `SELECT ... FOR UPDATE` on the parent row, a unique key with retry, or an auto-increment column.

**5. Inconsistent user IDs in inserts.**
The copay branch uses `$_SESSION['authId']` for `user_id` and `post_user`; the invoice branch uses `$_SESSION['authUserID']`. In portal mode, one of these is unset, which writes NULL or 0 into the audit trail. Use one identifier consistently.

**6. Account totals computed from formatted strings.**
Location: `$sum_balance += $balance * 1;` where `$balance = bucks(...)`.
`bucks()` returns a formatted currency string (symbol and thousands separators). Multiplying it by 1 will yield 0 or a truncated value, so the footer balance total is wrong. Sum the raw numeric values instead.

### Medium

**7. Unescaped output of patient-supplied card fields in the staff view.**
`echo $ccdata["cardNumber"] . "</span><br>";` and `echo $ccdata["cardNumber"]` are not escaped. Patient-entered data reaching a staff screen is a stored-XSS vector. Use `text()`.

**8. Undefined array index warnings.**
`$ccdata['authCode']` and `$ccdata['transId']` are read without `isset` when `$ccdata` is `array()` (no audit row). This emits notices on the page. Guard with `isset`.

**9. Hard-coded expiration years.**
The year dropdown is hard-coded to 2019–2028. It will go stale and reject valid cards. Generate it from the current year.

**10. Silent loss of `$gottoday` / "today" row logic.**
The removal of the "always show today's encounter" behavior and the `$dispdate = date(...)` override changes what patients see. This is not mentioned in the PR description and should be intentional and documented.

**11. Dead or unused code.**
`$isPortal` is set but never used in the diff. `flag` in the `paySubmit` handler is never meaningfully set. The duplicated `if (isset($_SESSION['authUserID']))` blocks in the form header could be a single conditional.

**12. Malformed HTML.**
`echo '<tr">';` has a stray quote. Also `'<htlm>'` (pre-existing typo) is still present. Both can break table rendering in some browsers.

**13. Unrelated changes bundled in the PR.**
The jQuery path changed from `jquery-1-11-3` to `jquery/dist/jquery.min.js` (may 404 if assets differ), `$(document).ready();` was removed, the copyright year was changed, and dozens of comment and whitespace changes were included. These obscure the substantive changes and make security review harder. Split the reformatting into a separate commit.

### Low

**14. Stripe and Authorize.Net scripts depend on external libraries not shown.**
`Stripe(...)` and `Accept.dispatchData(...)` require their respective JS libraries to be loaded. Confirm these are included in the gateway-specific branches.

**15. Inconsistent `$GLOBALS['payment_gateway']` checks.**
The modal uses `!= 'Stripe'` in one place and `== 'InHouse'` / `== 'AuthorizeNet'` elsewhere. An unexpected value renders no submit button at all. Add a default.

### Summary

The most serious problems are the stored and displayed CVV and full card number (critical), and the request-supplied patient ID that is not checked against the portal session (critical). Next are the lost encounter resolution, the sequence-number race, and the broken balance total. I recommend blocking the merge until items 1–4 are addressed and the reformatting is separated out.