## Review: portal_payment.php payment-flow refactor

This PR mixes a large UI/markup refactor with behavioral changes to payment posting and card handling. The behavioral changes carry most of the risk. I would not merge it as-is.

### Critical

**1. Portal user can post payments and read audit data for another patient (IDOR).**
- Location: `$pid = $_REQUEST['hidden_patient_code'] > 0 ? $_REQUEST['hidden_patient_code'] : $pid;` and `$recid = ...` / `getPortalAuditRec($recid)`.
- The session `pid` is overwritten by a client-supplied POST/GET parameter. Any logged-in portal patient can set `hidden_patient_code` (or `form_pid`) to another patient's pid and post payments or invoke the save path against that patient's billing and ar_session records.
- `$recid` is also taken from the request and used to load an audit record without checking that it belongs to the current `$pid`.
- The first line predates this PR, but the PR adds the `recid` path and makes the save path more consequential. Portal requests should use only the session pid, and any record lookup should be constrained to that pid.

**2. CVV (card security code) is now persisted and displayed.**
- Location: the `cardCode` field in the audit payload, and `<span id="cvvpin"><?php echo text($ccdata["cardCode"]) ?>`.
- Storing CVV after authorization violates PCI DSS, even encrypted. The previous code also stored it (`pin`), so this is not new in kind, but the PR keeps and displays it. The CVV should be used for the authorization request and then discarded.
- The full card number (`cardNumber`) is also stored and shown to staff. Only the last four digits should be retained and shown.

### High

**3. Non-atomic sequence number assignment.**
- Location: each `SELECT IFNULL(MAX(sequence_no),0)+1 ...` followed by an insert into `ar_activity`.
- Wrapping this in `sqlBeginTrans()`/`sqlCommitTrans()` does not prevent two concurrent requests from reading the same MAX and inserting duplicate `sequence_no` values. This needs a `SELECT ... FOR UPDATE`, a unique key, or a retry. The transaction wrapping is also inconsistent: the copay path uses it, while the invoice path wraps each insert separately.

**4. Removed encounter-resolution logic without explanation.**
- Location: the removed block `if ($_REQUEST['radio_type_of_payment'] == 'invoice_balance') ; else { if (!$enc) $enc = calendar_arrived($form_pid); }`.
- Payments with `$enc == 0` will now post against encounter 0 for the copay and cash paths. Either this removal is intended and the PR should say why, or it is a regression.

**5. Wrong `post_user` and inconsistent user IDs.**
- The copay path now records `$_SESSION['authId']` for `ar_session.user_id` and `$_SESSION['authUserID']` for `post_user`, and the invoice path uses `authUserID`. In portal-only sessions `authUserID` may be unset, which would post null or empty users. Use one consistent ID with a defined fallback.

**6. Broken HTML and PHP in the payment-type rows.**
- Location: `echo '<tr height="5"><td colspan="3"></td></tr><tr">';`
- The stray `"` makes an invalid `<tr>` tag. The `else` branch emits `<tr class="hidden">` and relies on the matching `</tr>` elsewhere, so the table structure now depends on the `isset($_SESSION['authUserID'])` branch. This should be restructured to emit complete rows in each branch.

### Medium

**7. Sum totals computed from formatted strings.**
- Location: `$sum_balance += $balance * 1;` where `$balance = bucks(...)`.
- `bucks()` returns a formatted currency string, so `* 1` may yield 0 or the wrong value, particularly with a currency symbol or thousands separator. Accumulate the numeric values before formatting.
- The sign convention is also inconsistent: `$sum_ptpaid += $ptpaid * -1` but `$sum_duept += $duept * 1`. Confirm the intended sign for each total.

**8. Undefined array index warnings.**
- `$ccdata['authCode']` and `$ccdata['transId']` are accessed when `$ccdata` may be an empty array (no audit record). Guard with `isset`.
- `$GLOBALS['payment_gateway']` is read in several places without `isset`.
- `$_REQUEST['hidden_patient_code']` is read without `isset`.

**9. Unused or unclear state.**
- `$isPortal` is set but not used in the portions shown.
- `$zero_enc` is assigned but not used.

**10. Missing dependencies not visible in the diff.**
- `getPortalAuditRec()` is called but not defined in this diff.
- The Stripe branch uses `Stripe(...)` and the Authorize.net branch uses `Accept.dispatchData`, but neither vendor script is included here. Confirm they are loaded.
- `paylib.php` must handle the new field names (`cardNumber`, `cardCode`, `cardHolderName`, `invValues`, `stripeToken`, etc.). Those changes are not in this PR.

**11. Incorrect HTML `pattern` attributes.**
- `pattern="\d"` on the card number and zip fields matches a single digit only, so a valid 5-digit zip or a full card number would fail constraint validation. The current JS avoids native submission, so this is latent, but it will break if the form is ever submitted natively. Use `\d{5}` (or `\d{5}(-\d{4})?` for zip) and a digit-and-space pattern for the card number, or drop the attributes.

**12. Cosmetic changes bundled into a functional PR.**
- Reformatting, comment removal, removed commented-out code, a changed jQuery asset path (`jquery/dist/jquery.min.js` vs `jquery-1-11-3/dist/jquery.js`), changed copyright year, and the `$(document).ready();` removal are all mixed in with functional changes. The asset path change can break the page if the file is absent. These changes make the real behavioral changes hard to review. Split them into a separate PR.

### Low

**13. Typos carried forward:** `<htlm>`, "comfirmation", "Aurhorize" (button id `payAurhorizeNet`), "compatable".

**14. Inline JS embeds API identifiers.** `apiKey` (Authorize.net `apiLoginID`) is emitted into page source. Confirm this is acceptable for the gateway; the client key is designed to be public, but the login ID generally should not be exposed.

### Summary

Do not merge until items 1 and 2 are fixed. Items 3–6 are correctness issues in the payment path and should also be resolved. The remaining items are robustness and maintainability concerns. I would also ask for the cosmetic refactor to be split out so the functional changes can be reviewed on their own.