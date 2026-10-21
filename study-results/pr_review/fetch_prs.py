import csv, json, subprocess, sys
REPO = "openemr/openemr"
def api(path):
    p = subprocess.run(["gh", "api", "-H", "Accept: application/vnd.github+json", path],
                       capture_output=True, text=True)
    if p.returncode:
        return {"_error": p.stderr.strip()[:200]}
    return json.loads(p.stdout)
out = []
for line in open(sys.argv[1]):
    cve, grp, sha, date, trace = line.split()
    c = api(f"repos/{REPO}/commits/{sha}")
    row = {"cve_id": cve, "group": grp, "intro_commit": sha, "intro_date": date, "traceable": trace,
           "commit_author": "", "committer": "", "pr_number": "", "pr_author": "", "merged_by": "",
           "approvals": "", "reviewers": "", "review_states": "", "review_comments": "", "issue_comments": "", "note": ""}
    if "_error" in c:
        row["note"] = "commit lookup failed: " + c["_error"]; out.append(row); continue
    row["commit_author"] = (c.get("author") or {}).get("login") or c["commit"]["author"]["name"]
    row["committer"] = (c.get("committer") or {}).get("login") or c["commit"]["committer"]["name"]
    prs = api(f"repos/{REPO}/commits/{c['sha']}/pulls")
    if isinstance(prs, dict) or not prs:
        row["note"] = "no PR associated (direct push or pre-GitHub history)"; out.append(row); continue
    pr = prs[0]
    n = pr["number"]
    full = api(f"repos/{REPO}/pulls/{n}")
    reviews = api(f"repos/{REPO}/pulls/{n}/reviews?per_page=100")
    reviews = reviews if isinstance(reviews, list) else []
    row.update(pr_number=n, pr_author=pr["user"]["login"],
               merged_by=(full.get("merged_by") or {}).get("login", ""),
               approvals=sum(r["state"] == "APPROVED" for r in reviews),
               reviewers=";".join(sorted({r["user"]["login"] for r in reviews if r.get("user")})),
               review_states=";".join(r["state"] for r in reviews),
               review_comments=full.get("review_comments", ""),
               issue_comments=full.get("comments", ""))
    if len(prs) > 1:
        row["note"] = "multiple PRs: " + ",".join(str(p["number"]) for p in prs)
    out.append(row)
w = csv.DictWriter(open(sys.argv[2], "w", newline=""), fieldnames=list(out[0]))
w.writeheader(); w.writerows(out)
