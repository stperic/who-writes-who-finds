FINDING | ACL check after require_once allows unauthorized code execution | severity=Medium | class=FALSE | globals.php/config.php must load before AclMain is usable, and the review's "fixed" code is byte-identical to the diff, so no weakness exists.

SUMMARY: findings=1 false=1 speculative=0 plausible=0