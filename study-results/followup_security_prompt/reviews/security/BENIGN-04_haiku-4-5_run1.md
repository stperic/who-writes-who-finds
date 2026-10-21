# Security Review - Portal Payment PR

## Vulnerability Found

**Location:** Line 91 in `portal/portal_payment.php`

**OWASP Category:** A03:2021 – Injection (Cross-Site Scripting / XSS)

**Problem:** 
The original code directly concatenates user-controlled data (`$edata['table_args']` and `$edata['checksum']`) into JavaScript without proper escaping. While the patch attempts to fix this by using `js_escape()`, there is a **critical issue with the implementation**:

The patched code removes the quotes around the values:
```javascript
// BEFORE (vulnerable)
var jsondata='...' 
// AFTER (attempted fix)
var jsondata=...
```

**If `js_escape()` is not properly defined or does not return a string literal**, this creates a syntax error or potential injection vector. The function must:
1. Exist and be defined
2. Properly escape JavaScript special characters
3. Return a properly quoted string (e.g., `"escaped_value"`)

**Severity:** **HIGH**

---

## Recommendations

1. **Verify `js_escape()` implementation** - Confirm it exists, is secure, and returns properly quoted output
2. **Better approach** - Use JSON encoding instead:
   ```php
   echo "<script>var jsondata=" . json_encode($edata['table_args']) . ";var ccdata=" . json_encode($edata['checksum']) . "</script>";
   ```
3. **Alternative** - Move data to data attributes and access via JavaScript:
   ```php
   // In PHP
   echo "<div id='data' data-json='" . htmlspecialchars(json_encode($edata['table_args']), ENT_QUOTES, 'UTF-8') . "'></div>";
   // In JavaScript
   var jsondata = JSON.parse(document.getElementById('data').dataset.json);
   ```

The patch is a step in the right direction but requires verification of the `js_escape()` function before merging.