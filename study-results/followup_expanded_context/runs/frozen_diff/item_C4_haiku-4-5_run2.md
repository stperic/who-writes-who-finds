# Code Review Issues

## Critical Security Issues

1. **SQL Injection Vulnerability** (Line 1925)
   - **Location**: `display_draw_image()` function, line 1925
   - **Problem**: `$sql = "SELECT * from documents where documents.url like '%".$filename."'";` - User-controlled `$filename` is directly concatenated into SQL query without parameterization
   - **Severity**: CRITICAL
   - **Fix**: Use parameterized queries: `sqlQuery("SELECT * from documents where documents.url like ?", array("%".$filename."%"))`

2. **SQL Injection Vulnerability** (Line 68)
   - **Location**: Line 68 in preference loading
   - **Problem**: While using `sqlStatement()` with parameters, the variable assignment `$$LOCATION = text($prefs['GOVALUE']);` creates dynamic variables that could be exploited
   - **Severity**: HIGH
   - **Recommendation**: Avoid variable variables; use associative arrays instead

3. **Unsafe File Path Handling** (Multiple locations)
   - **Location**: Lines 283-301, 1935-1955
   - **Problem**: File paths are constructed and used without proper validation. Paths from database could potentially be manipulated
   - **Severity**: HIGH
   - **Fix**: Validate and sanitize file paths before use

4. **Session-Based File Access** (Line 1943)
   - **Location**: `$_SESSION['site_id']` used directly in file path construction
   - **Problem**: If session data is compromised, file access can be manipulated
   - **Severity**: MEDIUM

## Reliability Issues

5. **Missing Variable Initialization** (Line 831)
   - **Location**: `$bad` variable used but never initialized
   - **Problem**: `if ($bad < '1')` references `$bad++` without prior initialization, results in undefined variable notice
   - **Severity**: MEDIUM
   - **Fix**: Initialize `$bad = 0;` before the loop

6. **Unreliable Variable Variable Usage** (Lines 755-772)
   - **Location**: Dynamic variable creation in wearing loop
   - **Problem**: Using `${"display_W_$count_rx"}` and similar patterns is error-prone and difficult to debug
   - **Severity**: MEDIUM
   - **Recommendation**: Use arrays instead of variable variables

7. **Missing Null Checks** (Multiple locations)
   - **Location**: Lines 109-116, 1921-1930
   - **Problem**: `$IMPPLAN_items` used in foreach without checking if it exists or is empty
   - **Severity**: MEDIUM
   - **Fix**: Add `if (!empty($IMPPLAN_items))` before foreach

## Maintainability Issues

8. **Extremely Long Function** (Lines 159-1916)
   - **Location**: `narrative()` function
   - **Problem**: ~1,700 lines of mixed HTML/PHP makes code unmaintainable
   - **Severity**: MEDIUM
   - **Recommendation**: Break into smaller functions, separate template logic

9. **Large Code Duplication** (Lines 486-1800)
   - **Location**: Repetitive table structures for different sections
   - **Problem**: Similar patterns repeated dozens of times (Visual Acuities, Refraction sections, etc.)
   - **Severity**: MEDIUM
   - **Recommendation**: Create helper functions for common patterns

10. **Inconsistent Escaping** (Throughout)
    - **Location**: Multiple lines use both `text()` and `echo` without `text()`
    - **Problem**: Line 1812 uses `echo report_ACT($NEURO_COMMENTS)` instead of `text()`; Line 1631 missing `text()` on `$CTLOSVA`
    - **Severity**: MEDIUM
    - **Fix**: Consistently use `text()` for all variable output

11. **Typo in Translation Key** (Line 803)
    - **Location**: `xlt('Constaast Visual Acuity')`
    - **Problem**: Should be "Contrast" not "Constaast"
    - **Severity**: LOW

12. **Deprecated Operator Usage** (Line 1631)
    - **Location**: `<?php echo ($CTLOSVA?:"-");`
    - **Problem**: Elvis operator `?:` is less readable than ternary `? : `
    - **Severity**: LOW

## Code Quality Issues

13. **Unclosed/Inconsistent PHP Tags** (Lines 420, 542)
    - **Location**: Mixed `<?` and `<?php` tags
    - **Problem**: Line 420 uses `<?` instead of `<?php`
    - **Severity**: LOW

14. **Logic Error** (Line 1606)
    - **Location**: `if (${"COMMENTS_$i"})` appears twice in similar contexts
    - **Problem**: Second occurrence should likely check different variable
    - **Severity**: LOW

15. **Browser Compatibility** (Line 894)
    - **Location**: CSS filter for IE: `filter: progid:DXImageTransform.Microsoft.Alpha(opacity=50)`
    - **Problem**: IE-specific code in modern application
    - **Severity**: LOW

---

## Summary
- **Critical Issues**: 1 (SQL injection in display_draw_image)
- **High Issues**: 2 (SQL injection in prefs, unsafe file paths)
- **Medium Issues**: 8 (Variable initialization, null checks, maintainability)
- **Low Issues**: 4 (Typos, deprecated syntax, browser support)

**Recommendation**: Prioritize fixing SQL injection vulnerabilities immediately before merging.