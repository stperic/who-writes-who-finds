FINDING | ACL check before CSRF check leaks information | severity=Moderate | class=FALSE | ACL checks run on the authenticated session, not the token, so ordering reveals nothing about CSRF token validity and the described timing/probing attack is not supported by the code.

SUMMARY: findings=1 false=1 speculative=0 plausible=0