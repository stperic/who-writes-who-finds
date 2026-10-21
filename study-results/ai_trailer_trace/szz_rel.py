import json, re, subprocess
from collections import Counter, defaultdict
REPO = "/Users/eric/bugstudy/openemr"
def git(*a): return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="replace").stdout
ai = json.load(open("ai_commits.json"))
fixes = json.load(open("fixes.json"))
cands = {}
for line in git("log", "--remotes=origin/rel-*", "--not", "origin/master", "--since=2025-09-01", "--format=%H\t%cs\t%s").splitlines():
    h, d, s = line.split("\t", 2)
    if s.lower().startswith("merge commit from fork"): cands[h] = {"date": d, "src": "fork-merge", "ghsa": []}
for g, v in {}.items():
    for h in v["fixes"]:
        cands.setdefault(h, {"date": git("log", "-1", "--format=%cs", h).strip(), "src": "advisory-link", "ghsa": []})["ghsa"].append(g)
SKIP = re.compile(r"(^tests?/|/tests?/|\.md$|CHANGELOG|composer\.lock|package-lock|\.github/|phpstan|baseline)", re.I)
res = {}
for f, meta in cands.items():
    parent = git("rev-parse", f + "^1").strip()
    blamed = Counter(); kinds = defaultdict(set); files = []
    diff = git("diff", "-U0", "--no-color", "-M", parent, f)
    cur = None
    for l in diff.splitlines():
        if l.startswith("--- "):
            cur = l[6:] if l.startswith("--- a/") else None
            if cur and SKIP.search(cur): cur = None
            if cur: files.append(cur)
        m = re.match(r"@@ -(\d+)(?:,(\d+))? \+\d+(?:,\d+)? @@", l)
        if m and cur:
            start, cnt = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            if cnt > 0: rng, kind = (start, start + cnt - 1), "deleted"
            else: rng, kind = (max(1, start - 1), start + 2), "adjacent"
            out = git("blame", "-w", "--line-porcelain", "-L", f"{rng[0]},{rng[1]}", parent, "--", cur)
            for bl in out.splitlines():
                if re.match(r"^[0-9a-f]{40} \d+ \d+", bl):
                    h = bl.split()[0]; blamed[h] += 1; kinds[h].add(kind)
    hits = {h: {"lines": n, "kind": sorted(kinds[h]), **ai[h]} for h, n in blamed.items() if h in ai}
    res[f] = {**meta, "files": files, "blamed_total": sum(blamed.values()), "ai_hits": hits,
              "subject": git("log", "-1", "--format=%s", f).strip(), "body": git("log", "-1", "--format=%b", f).strip()[:400]}
json.dump(res, open("szz_rel.json", "w"), indent=1)
hit = {f: v for f, v in res.items() if v["ai_hits"]}
print(f"security-fix commits analyzed: {len(res)} (fork merges {sum(v['src']=='fork-merge' for v in res.values())}); fixes touching AI-tagged lines: {len(hit)}")
for f, v in sorted(hit.items(), key=lambda x: x[1]["date"]):
    print(f"\nFIX {f[:10]} {v['date']} {v['src']} {v['ghsa']} files={v['files'][:3]}")
    print("    ", v["body"].splitlines()[0][:120] if v["body"] else v["subject"][:120])
    for h, a in v["ai_hits"].items():
        print(f"   <- {h[:10]} {a['date']} {a['author'][:18]:18} lines={a['lines']}/{v['blamed_total']} {a['kind']} | {a['subject'][:70]} | {a['trailers'][0][:45]}")
