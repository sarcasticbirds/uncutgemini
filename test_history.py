"""Byte-only candidate-packet checks; never import/compile/execute history."""
import json
from pathlib import Path
import shutil
import tempfile
import unittest

import curate_history

ROOT = Path(__file__).parent / "historical-candidates"


class HistoryTests(unittest.TestCase):
    def test_pinned_candidates_hashes_blobs_and_unaccepted_status(self):
        self.assertIn("not accepted", curate_history.verify(ROOT))
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
