import csv, json, re, subprocess, sys
REPO = "/Users/eric/bugstudy/openemr"
def git(*a): return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True).stdout
def gh(p):
    r = subprocess.run(["gh", "api", p], capture_output=True, text=True)
    return json.loads(r.stdout) if r.returncode == 0 else {}
out = {}
for line in open("advisories.tsv", encoding="utf8"):
    ghsa, cve, pub, sev, patched, summary = line.rstrip("\n").split("\t")
    if pub < "2024-09-01": continue
    shas = set()
    adv = gh(f"advisories/{ghsa}")
    text = json.dumps(adv.get("references", [])) + (adv.get("description") or "")
    shas |= set(re.findall(r"openemr/openemr/commit/([0-9a-f]{7,40})", text))
    for p in re.findall(r"openemr/openemr/pull/(\d+)", text):
        pr = gh(f"repos/openemr/openemr/pulls/{p}")
        if pr.get("merge_commit_sha"): shas.add(pr["merge_commit_sha"])
    for key in [ghsa] + ([cve] if cve else []):
        shas |= set(git("log", "origin/master", "--format=%H", "-i", f"--grep={key}").split())
    full = set()
    for s in shas:
        h = git("rev-parse", "--verify", "-q", s + "^{commit}").strip()
        if h and git("merge-base", "--is-ancestor", h, "origin/master") == "" and subprocess.run(["git","-C",REPO,"merge-base","--is-ancestor",h,"origin/master"]).returncode == 0:
            full.add(h)
    out[ghsa] = {"cve": cve, "published": pub, "severity": sev, "summary": summary, "fixes": sorted(full)}
json.dump(out, open("fixes.json", "w"), indent=1)
n = len(out); found = sum(1 for v in out.values() if v["fixes"])
print(f"advisories since 2024-09: {n}; with fix commit on master: {found}; without: {n-found}")
