import csv, json, subprocess, sys
REPO = "openemr/openemr"
def api(p):
    r = subprocess.run(["gh", "api", "--paginate", p], capture_output=True, text=True)
    return json.loads(r.stdout.replace("][", ",")) if r.returncode == 0 and r.stdout.strip() else []
cves = {r["cve_id"]: r for r in csv.DictReader(open(sys.argv[1], encoding="utf8"))}
for pair in sys.argv[2:]:
    cve, n, base = pair.split(":")
    v = cves[cve]
    print(f"\n===== {cve} ({v['vuln_type']}, {v['owasp']}) PR #{n} file {base}")
    print("  VULN:", " ".join(v["notes"].split("TRACE")[-1].split())[:420])
    pr = api(f"repos/{REPO}/pulls/{n}")
    for c in api(f"repos/{REPO}/pulls/{n}/comments?per_page=100"):
        if c["path"].endswith(base) and (c.get("user") or {}).get("login") != pr["user"]["login"]:
            hunk = [l for l in c["diff_hunk"].splitlines() if l.strip()][-1].strip()[:110]
            print(f"  [{c['user']['login']} line {c.get('original_line')}] {' '.join(c['body'].split())[:260]}\n      on: {hunk}")
