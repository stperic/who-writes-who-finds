#!/usr/bin/env python3
"""Build the versioned, public Jev dataset and a blinded human packet.

No model calls. GETs only pinned public GitHub revisions, without credentials.
Raw responses are cached by URL hash; the resulting dataset is checked into the
study separately. Model inputs never contain selection strata or prior labels.
"""
import argparse
import json
from pathlib import Path
import re
from urllib.request import Request, urlopen

from jev import ROOT, digest, read_json, write_json

V2 = ROOT / "jev-study/v2"
ARCHIVE = ROOT / "jev-study/results/2026-10-18-jev-1.14"
HOLDOUT = [
    ("openemr/openemr", "0cb7ccc25dcf", "portal/sign/lib/save-signature.php", "signature", "historical_vulnerable", "patient authorization and signature data"),
    ("openemr/openemr", "a29c0f7ac097", "portal/sign/lib/save-signature.php", "signature", "secure_fix", "patient authorization and signature data"),
    ("openemr/openemr", "1ab6846ed00f", "interface/main/backup.php", "backup", "historical_vulnerable", "shell construction and backup data"),
    ("openemr/openemr", "7bc7bd077a62", "interface/main/backup.php", "backup", "secure_fix", "shell construction and backup data"),
    ("openemr/openemr", "f6d98d0102df", "interface/billing/get_claim_file.php", "claim", "secure_fix", "authorization and claim data"),
    ("django-tenants/django-tenants", "db7dab14a63ffaf42b03954cbaa76aad52b1bbbd", "django_tenants/middleware/main.py", "tenant-host", "public_change", "tenant fallback ambiguity"),
    ("django-tenants/django-tenants", "d73abdaec0b024410e72681890a397f7256e0198", "django_tenants/middleware/main.py", "tenant-host", "secure_fix", "host and tenant enforcement"),
    ("openemr/openemr", "be104434f7b152ddf164e7025ad4aaec56fcf8dd", "composer.json", "tool-dependency", "public_change", "development dependency declaration"),
    ("openemr/openemr", "7f938df2c2d1328963e62e50120a3ac4777823ce", "README.md", "docs-badge", "routine", "static documentation"),
]


def fetch(url, cache):
    path = cache / digest(url)
    if not path.exists():
        request = Request(url, headers={"User-Agent": "Jev-public-study"})
        with urlopen(request, timeout=45) as response:
            data = response.read()
        path.write_bytes(data)
    return path.read_text()


def file_blocks(patch):
    return ["diff --git " + block for block in patch.split("diff --git ")[1:]]


def paths(diff):
    return list(dict.fromkeys(re.findall(r"^\+\+\+ b/(.+)$", diff, re.M)))


def no_advisory(text):
    if re.search(r"\b(?:CVE-\d{4}-\d+|GHSA-[a-z0-9-]+)\b", text, re.I):
        raise ValueError("Advisory identifier in blinded input; review selection before continuing")


def build(destination, cache):
    if destination.exists():
        raise ValueError("Destination exists; never overwrite a versioned dataset")
    cache.mkdir(parents=True, exist_ok=True)
    old = read_json(ARCHIVE / "answer-key.json")["cases"]
    provenance = {c["item"]: c for c in read_json(ARCHIVE / "public-provenance.json")}
    sources = []
    for case in old:
        source = provenance[case["item_id"]]
        diff = read_json(ARCHIVE / "inputs" / (case["item_id"] + ".json"))["diff"]
        family = {"item_01": "careteam", "item_03": "careteam", "item_02": "sql-builder", "item_10": "sql-builder"}.get(case["item_id"], case["item_id"])
        sources.append({"id": "D" + case["item_id"][-2:], "partition": "development", "family": family,
                        "kind": case["kind"], "synthetic": case["kind"].startswith("synthetic"),
                        "legacy_item": case["item_id"], "source_id": case["source_id"], "diff": diff,
                        "repo": "openemr/openemr" if "url" in source else None,
                        "revision": source.get("url", "").split("/commit/")[-1].removesuffix(".patch") or None})
    for i, (repo, sha, path, family, kind, coverage) in enumerate(HOLDOUT, 1):
        patch = fetch(f"https://github.com/{repo}/commit/{sha}.patch", cache)
        full_sha = re.search(r"^From ([a-f0-9]{40}) ", patch).group(1)
        blocks = [b for b in file_blocks(patch) if path in paths(b)]
        if len(blocks) != 1:
            raise ValueError(f"Expected one file patch for {path}")
        diff = blocks[0].split("\n-- \n")[0]
        sources.append({"id": f"H{i:02}", "partition": "holdout", "family": family, "kind": kind,
                        "synthetic": False, "repo": repo, "revision": full_sha, "diff": diff,
                        "selection_coverage": coverage, "scope": "single file change, not whole PR"})
    prepared = []
    for source in sources:
        diff = source.pop("diff")
        no_advisory(diff)
        context = []
        if source["repo"]:
            # Resolve all development abbreviated revisions using the public patch.
            patch = fetch(f'https://github.com/{source["repo"]}/commit/{source["revision"]}.patch', cache)
            source["revision"] = re.search(r"^From ([a-f0-9]{40}) ", patch).group(1)
            for path in paths(diff):
                url = f'https://raw.githubusercontent.com/{source["repo"]}/{source["revision"]}/{path}'
                text = fetch(url, cache)
                no_advisory(text)
                context.append({"path": path, "text": text})
        payload = {"diff": diff, "historical_context": context,
                   "context_scope": "Full touched postimage files at this change's revision only. Callers and external invariants may be missing." if context else "Synthetic diff only; no historical repository exists."}
        prepared.append((source, payload))
    destination.mkdir(parents=True)
    (destination / "inputs").mkdir()
    (destination / "packet").mkdir()
    manifest = {"version": "jev-dataset-v2.0", "holdout_status": "unqueried_pending_independent_human_adjudication",
                "selection": "Purposeful coverage selection before any holdout Jev calls. Public history may have been seen during model training. Holdout is relative to this Jev development set, not the broader vulnerability corpus.",
                "excluded": ["CVE-2026-23627: document-flow lineage overlaps development item_13", "CVE-2026-33918 introducing root import: not a realistic review change; only its fix included"], "cases": []}
    forms = []
    # Deterministic mixing prevents an obvious development/holdout grouping.
    blinded = sorted(prepared, key=lambda pair: digest("jev-v2-packet:" + pair[0]["id"]))
    blind_ids = {source["id"]: f"case_{n:02}" for n, (source, _) in enumerate(blinded, 1)}
    for source, payload in prepared:
        item = source["id"]
        source["blind_id"] = blind_ids[item]
        source["input"] = f"inputs/{item}.json"
        source["input_sha256"] = digest(json.dumps(payload, sort_keys=True))
        source["diff_sha256"] = digest(payload["diff"])
        write_json(destination / source["input"], payload)
        # Only neutral IDs, source code and historical context enter the packet.
        write_json(destination / "packet" / (source["blind_id"] + ".json"), payload)
        manifest["cases"].append(source)
    for source, _ in blinded:
        forms.append({"case_id": source["blind_id"], "required": None, "optional": None, "prohibited": None,
                      "context_sufficient": None, "missing_context": [], "rationale": "",
                      "reviewer": "", "reviewed_at": "", "independent_human": False,
                      "saw_model_outputs_or_prior_labels": None})
    write_json(destination / "manifest.json", manifest)
    write_json(destination / "packet/blank-labels.json", {"status": "pending", "cases": forms})
    draft = []
    for source, _ in prepared:
        if source["partition"] == "development":
            legacy = next(c for c in old if c["item_id"] == source["legacy_item"])
            draft.append({"id": source["id"], "required": legacy["required"], "optional": legacy["optional"],
                          "prohibited": sorted(set(read_json(ARCHIVE / "policy.json")["routes"]) - set(legacy["required"] + legacy["optional"])),
                          "rationale": legacy["rationale"]})
    write_json(destination / "development-draft-labels.json", {"status": "legacy_draft_unchanged_not_adjudicated", "cases": draft})
    return {"cases": len(prepared), "holdout": len(HOLDOUT), "packet": str(destination / "packet")}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--cache", type=Path, default=ROOT / "build/jev-v2-public/cache")
    args = parser.parse_args()
    print(json.dumps(build(args.destination, args.cache), indent=2))
