import csv, json, re, subprocess, sys
REPO = "openemr/openemr"
def api(p):
    r = subprocess.run(["gh", "api", "--paginate", p], capture_output=True, text=True)
    return json.loads(r.stdout.replace("][", ",")) if r.returncode == 0 else []
cves = {r["cve_id"]: r for r in csv.DictReader(open(sys.argv[2], encoding="utf8"))}
rows = list(csv.DictReader(open(sys.argv[1])))
for r in rows:
    if r["cve_id"] == "CVE-2026-24898" and not r["pr_number"]:
        pr = api(f"repos/{REPO}/pulls/1949")
        r["pr_number"], r["pr_author"] = "1949", pr["user"]["login"]
        r["merged_by"] = (pr.get("merged_by") or {}).get("login", "")
        r["note"] = "PR found via commit message (#1949)"
for r in rows:
    m = re.search(r"file=([^,\]\s]+)", cves[r["cve_id"]]["notes"])
    vfile = m.group(1) if m else ""
    r["vuln_file"] = vfile
    if not r["pr_number"]:
        r.update(other_reviewers="", other_approvals="", comments_on_vuln_file="", pr_touches_vuln_file="")
        continue
    n, author = r["pr_number"], r["pr_author"]
    reviews = api(f"repos/{REPO}/pulls/{n}/reviews?per_page=100")
    others = [x for x in reviews if x.get("user") and x["user"]["login"] != author]
    r["other_reviewers"] = ";".join(sorted({x["user"]["login"] for x in others}))
    r["other_approvals"] = sum(x["state"] == "APPROVED" for x in others)
    rc = api(f"repos/{REPO}/pulls/{n}/comments?per_page=100")
    base = vfile.rsplit("/", 1)[-1]
    r["comments_on_vuln_file"] = sum(1 for c in rc if base and c["path"].endswith(base) and c["user"]["login"] != author)
    files = api(f"repos/{REPO}/pulls/{n}/files?per_page=100")
    r["pr_touches_vuln_file"] = "yes" if any(base and f["filename"].endswith(base) for f in files) else ("no" if files else "unknown")
cols = ["cve_id","group","intro_commit","intro_date","traceable","commit_author","committer","pr_number","pr_author","merged_by",
        "other_reviewers","other_approvals","comments_on_vuln_file","pr_touches_vuln_file","vuln_file","note"]
w = csv.DictWriter(open(sys.argv[3], "w", newline=""), fieldnames=cols, extrasaction="ignore")
w.writeheader(); w.writerows(rows)
for r in rows:
    print(f"{r['cve_id']:15} {r['group']} PR={r['pr_number'] or '-':5} other_reviewers={r['other_reviewers'] or '-':26} approvals={str(r['other_approvals']):2} "
          f"comments_on_vuln_file={str(r['comments_on_vuln_file']):2} touches={r['pr_touches_vuln_file'] or '-':7} file={r['vuln_file'][-55:]}")
