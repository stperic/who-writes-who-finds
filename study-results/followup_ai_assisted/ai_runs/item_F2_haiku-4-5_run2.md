# Pull Request Review

I've found the following issues:

## 1. **Future-dated Copyright (Severity: High)**
**Location:** Line 15
```
@copyright Copyright (c) 2026 OpenCoreEMR Inc <https://opencoreemr.com/>
```
**Problem:** The copyright year is set to 2026, which is in the future. This should be the current year (2024 or 2025 depending on when this is being merged). This appears to be either a typo or a mistake.

**Recommendation:** Change to the current year.

---

## 2. **Race Condition in Directory Creation (Severity: Medium)**
**Location:** Lines 753-756
```php
if (!is_dir($eraDir) && !mkdir($eraDir, 0755, true) && !is_dir($eraDir)) {
    die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");
}
```
**Problem:** There's a TOCTOU (time-of-check-time-of-use) race condition. Between checking `!is_dir($eraDir)` and calling `mkdir()`, another process could create the directory. Additionally, `mkdir()` with `recursive=true` can fail for reasons other than the directory existing (permissions, disk space, etc.), but the second `is_dir()` check might pass if the directory was created by another process. This could mask other errors.

**Recommendation:** Simplify to:
```php
if (!is_dir($eraDir)) {
    if (!mkdir($eraDir, 0755, true)) {
        die(xlt("Cannot create ERA directory") . " '" . text($eraDir) . "'");
    }
}
```
Or use a try-catch if `mkdir()` throws exceptions in this codebase.

---

## 3. **Inconsistent Global Access Pattern (Severity: Low)**
**Location:** Lines 753-759
```php
$eraDir = OEGlobalsBag::getInstance()->getString('OE_SITE_DIR') . "/documents/era";
```
**Problem:** The code switches from direct `$GLOBALS` access to using `OEGlobalsBag::getInstance()`. While this may be an improvement, it's a refactoring that should be applied consistently across the file. Check if there are other `$GLOBALS` accesses in this file that should also be updated for consistency.

---

## Summary
- **1 High severity issue:** Fix the copyright year
- **1 Medium severity issue:** Fix the TOCTOU race condition in directory creation
- **1 Low severity issue:** Ensure consistent patterns for global access