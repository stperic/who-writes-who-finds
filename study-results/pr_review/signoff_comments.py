import json, subprocess, sys
REPO = "openemr/openemr"
def api(p):
    r = subprocess.run(["gh", "api", "--paginate", p], capture_output=True, text=True)
    return json.loads(r.stdout.replace("][", ",")) if r.returncode == 0 and r.stdout.strip() else []
for n in sys.argv[1:]:
    pr = api(f"repos/{REPO}/pulls/{n}")
    author = pr["user"]["login"]
    print(f"\n===== PR #{n} by {author}, merged_by={(pr.get('merged_by') or {}).get('login')} merged_at={pr.get('merged_at')} | {pr['title'][:70]}")
    for c in api(f"repos/{REPO}/issues/{n}/comments?per_page=100"):
        if (c.get("user") or {}).get("login") != author:
            print(f"  [conv] {(c.get("user") or {}).get("login")} {c['created_at'][:10]}: {' '.join(c['body'].split())[:220]}")
    for r in api(f"repos/{REPO}/pulls/{n}/reviews?per_page=100"):
        if (r.get("user") or {}).get("login") != author and r.get("body"):
            print(f"  [review {r['state']}] {(r.get("user") or {}).get("login")}: {' '.join(r['body'].split())[:220]}")
