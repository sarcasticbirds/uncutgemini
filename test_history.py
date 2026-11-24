"""Byte-only candidate-packet checks; never import/compile/execute history."""
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import subprocess
import sys
import unittest

import curate_history

ROOT = Path(__file__).parent / "historical-candidates"


class HistoryTests(unittest.TestCase):
    def reject_mutation(self, name, mutate, cli=False):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "packets"
            shutil.copytree(ROOT, root)
            packet = root / name / "packet.json"
            metadata = json.loads(packet.read_text())
            mutate(root / name, metadata)
            packet.write_text(json.dumps(metadata))
            with self.assertRaises(ValueError):
                curate_history.verify(root)
            if cli:
                result = subprocess.run([sys.executable, str(ROOT.parent / "curate_history.py"),
                                         str(root), "--verify"], capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("verification failed", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_untrusted_only_negative_matrix(self):
        # Never mutate history_expectations.json or verifier constants. Cover
        # every required field and every artifact type in BOTH real packets.
        for name, *_ in curate_history.PACKETS:
            original = json.loads((ROOT / name / "packet.json").read_text())
            def empty(directory, metadata):
                for path in directory.iterdir():
                    if path.is_dir():
                        shutil.rmtree(path)
                    else:
                        path.unlink()
                metadata["artifacts"] = []
            with self.subTest(name=name, mutation="empty"):
                self.reject_mutation(name, empty, cli=True)
            for field in original:
                with self.subTest(name=name, missing_packet_field=field):
                    self.reject_mutation(name, lambda d, m, f=field: m.pop(f))
            for field in ("candidate", "before_sha", "fix_sha", "introduction_sha", "source_repository"):
                with self.subTest(name=name, forged_packet_field=field):
                    self.reject_mutation(name, lambda d, m, f=field: m.update({f: "forged"}))
            for index, artifact in enumerate(original["artifacts"]):
                for field in artifact:
                    with self.subTest(name=name, artifact=index, missing_field=field):
                        self.reject_mutation(name, lambda d, m, i=index, f=field: m["artifacts"][i].pop(f))
                    with self.subTest(name=name, artifact=index, forged_field=field):
                        self.reject_mutation(name, lambda d, m, i=index, f=field:
                                             m["artifacts"][i].update({f: "forged"}))
                def omit(directory, metadata, i=index):
                    (directory / metadata["artifacts"].pop(i)["path"]).unlink()
                def forge(directory, metadata, i=index):
                    item = metadata["artifacts"][i]
                    data = b"forged source bytes\n"
                    (directory / item["path"]).write_bytes(data)
                    item.update(bytes=len(data), sha256=hashlib.sha256(data).hexdigest())
                    if "git_blob" in item:
                        item["git_blob"] = hashlib.sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()
                with self.subTest(name=name, artifact=index, mutation="omit entry and file"):
                    self.reject_mutation(name, omit)
                with self.subTest(name=name, artifact=index, mutation="omit entry only"):
                    self.reject_mutation(name, lambda d, m, i=index: m["artifacts"].pop(i))
                with self.subTest(name=name, artifact=index, mutation="omit file only"):
                    self.reject_mutation(name, lambda d, m, i=index: (d / m["artifacts"][i]["path"]).unlink())
                with self.subTest(name=name, artifact=index, mutation="recomputed forgery"):
                    self.reject_mutation(name, forge, cli=True)
            mutations = {
                "duplicate": lambda d, m: m["artifacts"].append(m["artifacts"][0].copy()),
                "unknown entry": lambda d, m: m["artifacts"].append({"path": "unexpected.txt"}),
                "unknown file": lambda d, m: (d / "unexpected.txt").write_text("extra"),
                "unknown directory": lambda d, m: (d / "unexpected").mkdir(),
                "escape": lambda d, m: m["artifacts"][0].update(path="../../outside"),
                "absolute": lambda d, m: m["artifacts"][0].update(path="/outside"),
                "noncanonical": lambda d, m: m["artifacts"][0].update(path="before/../" + m["artifacts"][0]["path"]),
                "empty metadata": lambda d, m: m.clear(),
                "null inventory": lambda d, m: m.update(artifacts=None),
                "extra field": lambda d, m: m.update(unexpected=True),
                "bool as int": lambda d, m: m.update(accepted_manifest=0),
            }
            for label, mutate in mutations.items():
                with self.subTest(name=name, mutation=label):
                    self.reject_mutation(name, mutate, cli=True)

    def test_symlinks_missing_packets_and_malformed_json_cli(self):
        for mutation in ("file-link", "directory-link", "packet-link", "missing-packet",
                         "extra-packet", "malformed", "duplicate-key", "non-object"):
            with self.subTest(mutation=mutation), tempfile.TemporaryDirectory() as temporary:
                root = Path(temporary) / "packets"
                shutil.copytree(ROOT, root)
                packet = root / "pr-statistics"
                if mutation.endswith("link"):
                    path = {"file-link": packet / "fix.diff", "directory-link": packet / "before",
                            "packet-link": packet}[mutation]
                    saved = Path(temporary) / "outside"
                    path.rename(saved)
                    path.symlink_to(saved, target_is_directory=saved.is_dir())
                elif mutation == "missing-packet":
                    shutil.rmtree(packet)
                elif mutation == "extra-packet":
                    (root / "unknown").mkdir()
                else:
                    (packet / "packet.json").write_text({"malformed": "{", "duplicate-key": '{"artifacts": [], "artifacts": []}',
                                                       "non-object": "null"}[mutation])
                result = subprocess.run([sys.executable, str(ROOT.parent / "curate_history.py"), str(root), "--verify"],
                                        capture_output=True, text=True)
                self.assertEqual(result.returncode, 1)
                self.assertEqual(result.stdout, "")
                self.assertIn("verification failed", result.stderr)
                self.assertNotIn("Traceback", result.stderr)

    def test_pinned_candidates_hashes_blobs_and_unaccepted_status(self):
        self.assertIn("not accepted", curate_history.verify(ROOT))
        result = subprocess.run([sys.executable, str(ROOT.parent / "curate_history.py"), str(ROOT), "--verify"],
                                env={"PATH": ""}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("candidate identity integrity", result.stdout)
        self.assertIn("not accepted", result.stdout)
        for name, _, _, _, _ in curate_history.PACKETS:
            metadata = json.loads((ROOT / name / "packet.json").read_text())
            self.assertTrue(metadata["remaining_evidence"])
            self.assertTrue(all(item["source_url"].startswith(curate_history.REPO) for item in metadata["artifacts"]))
            self.assertTrue(all(item["path"].endswith(".txt") for item in metadata["artifacts"] if "git_blob" in item))

    def test_packet_tampering_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "packets"
            shutil.copytree(ROOT, root)
            (root / "pr-statistics" / "before" / "action.yml.txt").write_text("tampered")
            with self.assertRaises(ValueError):
                curate_history.verify(root)

    def test_candidates_are_not_manifest_cases_or_scoring_slots(self):
        manifest = json.loads((ROOT.parent / "corpus" / "manifest.json").read_text())
        self.assertEqual(manifest["inventory"]["populated"]["historical"], 0)
        self.assertEqual(len(manifest["provisional_slots"]), 12)
        self.assertEqual(manifest["inventory"]["substantive_bugs"], 6)
        self.assertFalse(manifest["split_frozen"])
        self.assertFalse(any(case["category"] == "historical" for case in manifest["cases"]))


if __name__ == "__main__":
    unittest.main()
