"""Verify the compact study against its archived original and API records."""
import collections
import csv
import hashlib
import io
import json
import pathlib
import zipfile

HERE = pathlib.Path(__file__).resolve().parent
ARCHIVE = HERE / "evidence" / "study-results.zip"


def rows(path):
    with path.open(newline="") as handle:
        return list(csv.DictReader(handle))


def sha(data):
    return hashlib.sha256(data).hexdigest()


expected_archive_hash = (HERE / "evidence" / "SHA256.txt").read_text().split()[0]
assert sha(ARCHIVE.read_bytes()) == expected_archive_hash, "Archive SHA-256 mismatch"
manifest = rows(HERE / "evidence" / "archive-manifest.csv")
assert len(manifest) > 4900
with zipfile.ZipFile(ARCHIVE) as bundle:
    names = set(bundle.namelist())
    assert names == {r["path"] for r in manifest}
    for row in manifest:
        data = bundle.read(row["path"])
        assert len(data) == int(row["bytes"]) and sha(data) == row["sha256"], row["path"]
    for path in (HERE / "data" / "original").rglob("*"):
        if path.is_file():
            rel = "study-results/" + path.relative_to(HERE / "data" / "original").as_posix()
            assert path.read_bytes() == bundle.read(rel), rel
    for path in (HERE / "inputs").glob("*.diff"):
        assert path.read_bytes() == bundle.read(
            "study-results/followup_haiku_prompt_fullset/inputs/" + path.name)
    for path in (HERE / "prompts").glob("*.txt"):
        assert path.read_bytes() == bundle.read(
            "study-results/followup_haiku_prompt_fullset/prompts/" + path.name)

    matrix = rows(HERE / "data" / "case-matrix.csv")
    assert len(matrix) == 24
    assert collections.Counter(r["historical_haiku"] for r in matrix) == {"Caught": 8, "Partial": 7, "Missed": 9}
    assert collections.Counter(r["historical_sonnet"] for r in matrix) == {"Caught": 20, "Partial": 3, "Missed": 1}
    assert collections.Counter(r["new_haiku_generic"] for r in matrix) == {"Caught": 11, "Partial": 11, "Missed": 2}
    assert collections.Counter(r["new_haiku_security_touched"] for r in matrix) == {"Caught": 19, "Partial": 4, "Missed": 1}
    controls = rows(HERE / "data" / "prompt-followup" / "benign_scores.csv")
    assert len(controls) == 60
    assert sum(r["arm"] == "generic" and int(r["false"]) > 0 for r in controls) == 8
    assert sum(r["arm"] == "security_policy" and int(r["false"]) > 0 for r in controls) == 24
    for arm in ("generic", "security_policy"):
        for item in [f"item_{i:02d}" for i in range(1, 25)] + [f"BENIGN-{i:02d}" for i in range(1, 11)]:
            prompt = (HERE / "prompts" / f"{arm}.txt").read_text().replace(
                "{diff}", (HERE / "inputs" / f"{item}.diff").read_text().rstrip("\n"))
            for run in (1, 2, 3):
                stem = f"{item}_run{run}"
                base = f"study-results/followup_haiku_prompt_fullset/runs/{arm}/{stem}"
                request = json.loads(bundle.read(base + ".request.json"))
                review_meta = json.loads(bundle.read(base + ".meta.json"))
                assert request == {"model": "claude-haiku-4-5-20251001", "max_tokens": 16000,
                                   "messages": [{"role": "user", "content": prompt}]}
                assert review_meta["status"] == "ok" and review_meta["served_model"] == request["model"]
                assert review_meta["stop_reason"] == "end_turn"
                kind = "detect" if item.startswith("item_") else "benign"
                judge_path = f"study-results/followup_haiku_prompt_fullset/judge/{kind}/{arm}/{stem}.meta.json"
                judge = json.loads(bundle.read(judge_path))
                assert judge["status"] == "ok" and judge["judge_model"] == "claude-fable-5-1"
                if kind == "detect": assert judge["label"] in ("Caught", "Partial", "Missed")
    for row in matrix:
        assert (HERE / "cases" / f"{row['case_id']}.md").exists()
    for i in range(1, 11):
        assert (HERE / "controls" / f"BENIGN-{i:02d}.md").exists()

print(f"Verified archive ({len(manifest)} files), 24 cases, 10 controls, 204 review calls and 204 judge calls")
