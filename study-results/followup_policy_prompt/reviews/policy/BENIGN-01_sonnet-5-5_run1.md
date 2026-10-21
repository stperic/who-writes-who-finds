**Review of `SearchConfigClauseBuilder::buildSortOrderClauseFromConfig`**

The change fixes a real SQL injection hole. Previously `$search->getField()` was concatenated straight into `ORDER BY`. An exact-match whitelist with strict `in_array` is the right approach. I found no blocking problems in the diff itself, but these points need attention before merge.

1. **Breaking signature change (Medium–High, reliability).**
   - `$allowedColumns` is a new required parameter.
   - The diff does not touch any callers. Every existing call site, including services, REST controllers, and any module or third-party code, will throw `ArgumentCountError` at runtime.
   - Before merging, grep for `buildSortOrderClauseFromConfig` and confirm each caller is updated and supplies a sensible whitelist.
   - If callers can't all be updated, consider a transition plan. Don't make the parameter optional with a "no filtering" default, because that would reopen the injection.

2. **Silent dropping of invalid sort fields (Low–Medium, maintainability).**
   - A disallowed field is skipped with `continue`, with no logging or error.
   - A client sending a bad `_sort` value gets unsorted results with no feedback. A typo in a whitelist entry fails the same way.
   - Consider logging at debug or warning level, or returning a 400 at the API layer. That also helps spot probing attempts.
   - An empty whitelist silently disables sorting.

3. **Whitelist semantics are undocumented (Low).**
   - Matching is exact and case-sensitive. A column qualified with a table alias (`p.lname`) will not match a request for `lname`, and the reverse is also true.
   - The docblock should say whether entries are expected to be qualified, and that the whitelist must be developer-defined and never derived from request input.
   - Using the same whitelist for validation and for SQL output is safe here only because entries are trusted.

4. **Pre-existing exposure in related code (Medium, security, outside the diff).**
   - The same class, and `SearchFieldOrder::getField()` and its parsers, may still pass unvalidated field names or values into other SQL fragments. The `QueryUtils` import suggests other methods build SQL.
   - Audit sibling builders such as limit, offset, and other clause builders. Check that the field name is never used unescaped anywhere else.
   - This diff only protects callers of this one method.

5. **No tests (Low).** Add unit tests for these cases:
   - an allowed field
   - a disallowed field
   - an injection string such as `lname; DROP TABLE x`
   - a mix of valid and invalid fields
   - an empty whitelist
   - ASC and DESC

6. **Minor.**
   - The `array $allowedColumns` type hint could be `list<string>` in the docblock for static analysis.
   - The `empty()` to `=== []` change is fine.
   - Adding the new author and copyright line is unrelated to the fix and is fine to keep.