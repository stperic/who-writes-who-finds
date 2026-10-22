"""Judge the step 4 reviews with Claude Opus 5.5.

Usage: python3 -I judge_reviews.py <path-to-.env>

Judge: Claude Opus 5.5, the study author's choice (2026-10-21, before any step 4
review was judged). The earlier follow-ups were judged by Claude Fable 5.1;
Opus 5.5 is also one of the reviewers here. So that F1 diff-only vs
diff+context compares like with like, the 30 reused F1 diff-only reviews
(../followup_ai_assisted/ai_runs, ../followup_security_prompt/reviews/security_policy)
are re-judged here too; their Fable labels in those folders are unchanged.
A refused judge call is kept (.attempt<n> suffix) and retried up to twice.

Same judge prompt and rubric as ../followup_ai_assisted/judge.py (read from
that file); F1 ground truth from there too. Ground truth for C1-C4 below is
written from the study's verified trace notes in ../cves.csv. For the
security-prompt arms, the one judge sentence saying the prompt never
mentioned security is replaced, as in ../followup_security_prompt/.
Reviewer identity and arm are never shown. Each call stores
judge/<arm>__<name>.prompt.txt, .response.json and .md; results go to
judge_detection.csv with per-call usage.
"""
import ast, csv, json, pathlib, re, sys, time, urllib.error, urllib.request, datetime
from concurrent.futures import ThreadPoolExecutor

HERE = pathlib.Path(__file__).resolve().parent
STUDY = HERE.parent
KEY = next(l.split("=", 1)[1].strip().strip('"') for l in open(sys.argv[1]) if l.startswith("ANTHROPIC_API_KEY="))
JUDGE = "claude-opus-5-5"
REFUSAL_RETRIES = 2
src = (STUDY / "followup_ai_assisted" / "judge.py").read_text()
c = {n.targets[0].id: ast.literal_eval(n.value) for n in ast.parse(src).body
     if isinstance(n, ast.Assign) and isinstance(n.targets[0], ast.Name) and n.targets[0].id in ("RUBRIC", "TRUTH", "PROMPT")}
RUBRIC, PROMPT = c["RUBRIC"], c["PROMPT"]
OLD = "asked for an ordinary pre-merge review. The prompt\nnever mentioned security or any vulnerability."
NEW = "asked for a security-focused pre-merge review. The prompt\ndid not name this vulnerability."
assert PROMPT.count(OLD) == 1
PROMPT_SEC = PROMPT.replace(OLD, NEW)

TRUTH = {
    "item_F1": c["TRUTH"]["item_F1"],
    "item_C1": """CVE-2025-31121 (XSS, OWASP A03), file controllers/C_Document.class.php.
This change adds a fifth positional parameter, $disable_exit = false, to
C_Document::retrieve_action() and, when it is set, returns the raw document file contents
instead of exiting after sending them with the right Content-Type header. The legacy
Controller (library/classes/Controller.class.php) maps URL query parameters positionally onto
action arguments and echoes the action's return value with the default text/html content type.
So a request for a patient image with disable_exit=true makes the server return the raw file
bytes as text/html; HTML/JavaScript embedded in the image (for example in its EXIF title) runs
in the viewer's browser: stored cross-site scripting.""",
    "item_C2": """CVE-2026-24487 (broken access control / cross-patient data exposure, OWASP A01), file
src/Services/FHIR/FhirCareTeamService.php. This change rewrites the FHIR CareTeam service: it
removes the service's own getOne() override that scoped results to the requested patient, adds
getPatientContextSearchField(), and implements IResourceUSCIGProfileService but not
IPatientCompartmentResourceService. FhirServiceBase::getAll() applies patient-context filtering
only when the service is an instance of IPatientCompartmentResourceService, so for
patient-scoped API access (for example a SMART patient-context token) CareTeam requests are no
longer filtered by patient and return care teams for every patient in the system.""",
    "item_C3": """CVE-2026-25146 (exposure of a secret credential, OWASP A05), file portal/portal_payment.php.
This change adds client-side JavaScript to the patient portal payment page that renders the
payment gateway's API key into the page: var apiKey = <?php echo json_encode($GLOBALS['gateway_api_key']); ?>;
The gateway_api_key global holds the gateway's private secret key (for Stripe, the secret API
key); only for Authorize.Net is the matching value a public login identifier. Every portal user
who opens the page can read the private key from the page source and use it against the
practice's payment account.""",
    "item_C4": """CVE-2026-33321 (server-side request forgery, OWASP A10), file interface/forms/eye_mag/report.php.
This change adds the eye exam report, which echoes stored, user-supplied values without
escaping into HTML and into CSS url() contexts (for example background: <?php echo $background; ?>
and free-text fields such as HPI, motility, visual field, Rx type and plan/order details). The
patient report page renders forms' report.php output server-side into a PDF with an HTML-to-PDF
renderer, which fetches URLs in the markup. Injected URLs are therefore fetched by the server:
out-of-band server-side request forgery. The root cause is the missing output escaping; the
same flaw also allows HTML injection in the browser view.""",
}

def ask(prompt):
    body = json.dumps({"model": JUDGE, "max_tokens": 16000, "messages": [{"role": "user", "content": prompt}]}).encode()
    err = None
    for attempt in range(6):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": KEY, "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            return json.load(urllib.request.urlopen(req, timeout=900)), None
        except urllib.error.HTTPError as e:
            err = f"HTTP {e.code}"
            if e.code in (429, 500, 502, 503, 529) and attempt < 5: time.sleep(min(120, 10 * 2 ** attempt)); continue
            return None, err
        except Exception as e:
            err = str(e)[:150]
            if attempt < 5: time.sleep(15); continue
    return None, err

REUSED = {"frozen_diff": STUDY / "followup_ai_assisted" / "ai_runs",
          "secpol_diff": STUDY / "followup_security_prompt" / "reviews" / "security_policy"}
sources = [(f.parent.name, f) for f in sorted((HERE / "runs").rglob("*.md"))]
sources += [(arm, f) for arm, d in REUSED.items() for f in sorted(d.glob("item_F1_*.md"))]
jobs = []
for arm, f in sources:
    name = f.stem
    item = "_".join(name.split("_")[:2])
    tmpl = PROMPT_SEC if arm.startswith("secpol") else PROMPT
    jobs.append((arm, name, item, str(f.relative_to(STUDY)),
                 tmpl.format(rubric=RUBRIC, truth=TRUTH[item], review=f.read_text().strip())))

def run(job):
    arm, name, item, source, prompt = job
    d = HERE / "judge"; d.mkdir(exist_ok=True)
    base = d / f"{arm}__{name}"
    md, rj = base.with_suffix(".md"), base.with_suffix(".response.json")
    prior = len(list(d.glob(base.name + ".response.json.attempt*")))
    if md.exists() and md.read_text().strip() and json.loads(rj.read_text()).get("stop_reason") != "refusal":
        return arm, name, item, source, md.read_text(), json.loads(rj.read_text()), prior + 1
    base.with_suffix(".prompt.txt").write_text(prompt)
    for attempt in range(prior + 1, prior + REFUSAL_RETRIES + 2):
        resp, err = ask(prompt)
        if resp is None:
            resp = {"error": err}
        rj.write_text(json.dumps(resp, indent=1))
        text = "".join(b.get("text", "") for b in resp.get("content", []) if b.get("type") == "text")
        md.write_text(text)
        if resp.get("stop_reason") != "refusal" or attempt > prior + REFUSAL_RETRIES:
            break
        for f in (md, rj):
            f.rename(f.with_name(f.name + f".attempt{attempt}"))
    return arm, name, item, source, text, resp, attempt

rows = []
with ThreadPoolExecutor(max_workers=4) as pool:
    for arm, name, item, source, text, resp, attempts in pool.map(run, jobs):
        m = re.findall(r"LABEL:\s*\**\s*(Caught|Partial|Missed)", text)
        slug, run_no = name[len(item) + 1:].rsplit("_run", 1)
        u = resp.get("usage") or {}
        rows.append({"arm": arm, "item": item, "model_slug": slug, "run": run_no, "judge_label": m[-1] if m else "",
                     "source": source, "judge_model": resp.get("model"), "judge_attempts": attempts,
                     "stop_reason": resp.get("stop_reason") or resp.get("error"), "response_id": resp.get("id"),
                     "input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
                     "utc": datetime.datetime.now(datetime.UTC).isoformat(timespec="seconds")})
        print(arm, name, rows[-1]["judge_label"] or "??", rows[-1]["stop_reason"], flush=True)
rows.sort(key=lambda r: (r["arm"], r["item"], r["model_slug"], r["run"]))
with open(HERE / "judge_detection.csv", "w", newline="") as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
print("judge calls:", len(rows), "input tokens:", sum(r["input_tokens"] or 0 for r in rows), "output tokens:", sum(r["output_tokens"] or 0 for r in rows))
