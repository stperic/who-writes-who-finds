# Security Review: `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`

## Verdict: No security vulnerabilities found

This diff fixes a vulnerability rather than introducing one.

### What the change fixes (A03:2021 – Injection)

Before this change, `$search->getField()` was concatenated directly into the `ORDER BY` clause. Column names and sort directions can't be bound as prepared-statement parameters. So if a sort field came from user input (for example, a FHIR or REST `_sort` parameter), an attacker could inject SQL, such as:

```
_sort=(SELECT CASE WHEN (SELECT SUBSTR(password,1,1) FROM users_secure LIMIT 1)='a' THEN pid ELSE fname END)
```

This is a classic blind SQL injection through `ORDER BY`. In an EHR holding PHI, that would be **High/Critical**.

### Why the new code is sound

| Aspect | Assessment |
|---|---|
| Whitelist check | `in_array($field, $allowedColumns, true)` uses strict comparison, which avoids PHP type-juggling bypasses. |
| Sort direction | Derived from a boolean and emitted only as the literals `ASC` or `DESC`, never from user input. |
| Fail-closed behavior | Unlisted fields are skipped. If nothing is valid, an empty string is returned. |
| Required parameter | `$allowedColumns` has no default. A caller that hasn't been updated throws an `ArgumentCountError` instead of silently running unfiltered. |
| Empty-clause handling | Returning `""` when all fields are filtered prevents malformed SQL such as `ORDER BY ` with nothing after it. |

## Non-blocking recommendations

1. **Caller discipline (Informational).** The protection is only as strong as the whitelist. Confirm that every call site passes a hard-coded or schema-derived array, never anything built from request data. A grep for all callers in this PR or a follow-up would confirm full coverage. A docblock note saying "must not contain user-controlled values" would also help.

2. **Logging rejected sort fields (Low, A09:2021 – Security Logging and Monitoring Failures).** Invalid fields are dropped silently. A debug or warning log entry for rejected fields would help detect probing attempts and also surface legitimate bugs where a valid column was left out of a whitelist.

3. **Silent ignore vs. explicit error (Informational, design).** Ignoring an invalid sort parameter is safe. However, for API consumers, a FHIR- or REST-appropriate 400 response may be clearer than results returned in an unexpected order. Either choice is acceptable from a security standpoint.

**Recommendation: Approve.** Follow-up item #1 should be confirmed before or shortly after merging.