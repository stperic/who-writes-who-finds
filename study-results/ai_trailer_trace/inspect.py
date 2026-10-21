import json, re, subprocess, sys
REPO = "/Users/eric/bugstudy/openemr"
def git(*a): return subprocess.run(["git", "-C", REPO, *a], capture_output=True, text=True, errors="replace").stdout
szz = json.load(open("szz.json")); ai = json.load(open("ai_commits.json"))
for f, v in sorted(szz.items(), key=lambda x: x[1]["date"]):
    if not v["ai_hits"]: continue
    parent = git("rev-parse", f + "^1").strip()
    print(f"\n######## FIX {f[:10]} {v['date']} {v['ghsa']}")
    diff = git("diff", "-U0", "--no-color", parent, f, "--", *v["files"])
    cur = None
    for l in diff.splitlines():
        if l.startswith("--- a/"): cur = l[6:]
        m = re.match(r"@@ -(\d+)(?:,(\d+))? ", l)
        if m and cur:
            s, c = int(m.group(1)), int(m.group(2) if m.group(2) is not None else 1)
            rng = (s, s + c - 1) if c else (max(1, s - 1), s + 2)
            out = git("blame", "-w", "--line-porcelain", "-L", f"{rng[0]},{rng[1]}", parent, "--", cur).splitlines()
            i = 0; h = None; prev = None
            for bl in out:
                if re.match(r"^[0-9a-f]{40} \d+ \d+", bl): h = bl.split()[0]; prev = None
                elif bl.startswith("previous "): prev = bl.split()[1:]
                elif bl.startswith("\t") and h in ai:
                    old = ""
                    if prev:
                        # what did this line look like before the AI commit? search the AI commit's diff for a removed line nearby
                        d = git("show", "-U0", "--no-color", h, "--", cur)
                        rem = [x[1:].strip() for x in d.splitlines() if x.startswith("-") and not x.startswith("---")]
                        new = bl[1:].strip()
                        toks = set(re.findall(r"\w+", new))
                        best = max(rem, key=lambda r: len(toks & set(re.findall(r"\w+", r))), default="")
                        old = best if toks & set(re.findall(r"\w+", best)) else "(no similar removed line: newly written)"
                    else:
                        old = "(file created by this commit)"
                    print(f"  {cur.split('/')[-1]}  AI {h[:10]} {ai[h]['subject'][:50]}")
                    print(f"     now : {bl[1:].strip()[:150]}")
                    print(f"     was : {old[:150]}")
