"""Copy two pinned historical candidates as inert evidence; never run their code.

Requires already-fetched local Git objects. No network, checkout, imports of
historical Python, shell/workflow execution, accepted-corpus or scoring writes.
Output must be new. Verification reads bytes only and needs no Git/network.
"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess

REPO = "https://github.com/sarcasticbirds/uncutgemini"
INTRO = "1c0a726ebf0f65d32ccf4281bc4b869c7789604d"
PACKETS = [
    ("review-validation", "71c51d8ceabddb7e04dc7f5707a19556f40d7acc", INTRO,
     ["review.py", "action.yml"], ["review.py", "action.yml", "test_review.py"]),
    ("pr-statistics", "1a59e878ea812907cd9c61e4e2366c6d1a4a9b72",
     "db4d0a86a150e278a5893fe1bf67c85a50f20e15",
     ["action.yml", "review.py"], ["action.yml", "review.py"]),
]


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(*args):
    return subprocess.run(["git", *args], check=True, capture_output=True).stdout


def require(condition):
    if not condition:
        raise ValueError("Historical packet integrity mismatch")


def collect(root):
    root.mkdir(parents=True, exist_ok=False)
    for name, fixed, parent, before_files, after_files in PACKETS:
        directory = root / name
        directory.mkdir()
        artifacts = []

        def save(path, data, **metadata):
            target = directory / path
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            artifacts.append({"path": path, "sha256": sha(data), "bytes": len(data), **metadata})

        def snapshot(role, commit, filename):
            blob = git("rev-parse", f"{commit}:{filename}").decode().strip()
            save(f"{role}/{filename}.txt", git("cat-file", "blob", blob),
                 role=role, source_path=filename, commit=commit, git_blob=blob,
                 source_url=f"{REPO}/blob/{commit}/{filename}")

        actual_parents = git("show", "-s", "--format=%P", fixed).decode().strip().split()
        if actual_parents != [parent]:
            raise ValueError("Unexpected fix parent")
        if git("show", "-s", "--format=%P", INTRO).strip():
            raise ValueError("Introduction is not repository root")
        for commit in [INTRO, parent, fixed]:
            # Prove these are actual source ancestors, not reversed authored fixes.
            git("merge-base", "--is-ancestor", commit, fixed)
        for role, commit, files in [("before", parent, before_files), ("fixed", fixed, after_files),
                                     ("introduction", INTRO, [before_files[0]])]:
            for filename in files:
                snapshot(role, commit, filename)
        for role, commit in [("before", parent), ("fixed", fixed), ("introduction", INTRO)]:
            snapshot(role, commit, "LICENSE")
        paths = ["review.py", "test_review.py"] if name == "review-validation" else ["action.yml"]
        save("fix.diff", git("diff", "--no-ext-diff", "--no-textconv", "--full-index", parent, fixed, "--", *paths),
             source_url=f"{REPO}/commit/{fixed}", kind="actual-forward-fix-diff")
        save("introduction.diff", git("diff-tree", "--root", "--no-commit-id", "--no-ext-diff", "--no-textconv",
                                      "--full-index", "-p", INTRO, "--", before_files[0]),
             source_url=f"{REPO}/commit/{INTRO}", kind="actual-root-addition-not-reversed-fix")
        for role, commit in [("before", parent), ("fixed", fixed), ("introduction", INTRO)]:
            save(role + "/commit.txt", git("show", "-s", "--format=%H%n%P%n%B", commit),
                 source_url=f"{REPO}/commit/{commit}", kind="git-commit-id-parents-message")
        metadata = {
            "schema_version": 1, "candidate": name, "status": "development-visible-candidate-not-adjudicated",
            "source_repository": REPO, "before_sha": parent, "fix_sha": fixed,
            "introduction_sha": INTRO, "introduction_parents": [],
            "introduction_scope": "First observed addition in this repository root; no earlier good parent or upstream lineage established",
            "access_basis": "Assigned authorized repository; managed bird-hawk git/gh read access verified",
            "license_basis": "MIT license copied verbatim at introduction, before and fixed revisions",
            "redaction_basis": "Repository source only; exact bytes retained, no private sources/credentials requested or added. Source inspection found symbolic environment references, not credential values; no independent redaction certification",
            "execution": "No historical source imported, compiled, executed or workflows run; source/diff inspection and authored static reasoning only",
            "accepted_manifest": False, "fresh_holdout": False, "independent_adjudication": False,
            "remaining_evidence": ["Independent source/contract/root-cause adjudication and redaction audit",
                                   "Observed failing input/response or historical run log and pinned external API/CLI contract",
                                   "No pre-introduction good parent exists in this repository; upstream lineage unknown"],
            "artifacts": artifacts}
        (directory / "packet.json").write_text(json.dumps(metadata, sort_keys=True, indent=2) + "\n")


def verify(root):
    for name, fixed, parent, _, _ in PACKETS:
        directory = root / name
        metadata = json.loads((directory / "packet.json").read_text())
        require((metadata["candidate"], metadata["fix_sha"], metadata["before_sha"]) == (name, fixed, parent))
        require(metadata["introduction_sha"] == INTRO and metadata["introduction_parents"] == [])
        require(metadata["accepted_manifest"] is False and metadata["fresh_holdout"] is False)
        require(metadata["independent_adjudication"] is False)
        for artifact in metadata["artifacts"]:
            path = (directory / artifact["path"]).resolve()
            require(path.is_relative_to(directory.resolve()))
            data = path.read_bytes()
            require(len(data) == artifact["bytes"] and sha(data) == artifact["sha256"])
            if "git_blob" in artifact:
                require(hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest() == artifact["git_blob"])
    return "Two development-visible candidate packets verified; not accepted corpus cases"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--verify", action="store_true")
    args = parser.parse_args()
    if not args.verify:
        collect(args.output)
    print(verify(args.output))
