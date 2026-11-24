"""Offline corpus integrity, runtime-boundary and denominator regressions."""
import copy
import datetime
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

import build_corpus
import offline
import runtime

ROOT = Path(__file__).parent / "corpus"


class OfflineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name) / "corpus"
        shutil.copytree(ROOT, self.root)

    def save_manifest(self, manifest):
        (self.root / "manifest.json").write_text(json.dumps(manifest))
        (self.root / "manifest.sha256").write_text(offline.sha(self.root / "manifest.json"))

    def mutate_artifact(self, manifest, case, name, value):
        ref = case["artifacts"][name]
        path = self.root / ref["path"]
        path.write_text(json.dumps(value))
        ref["sha256"] = offline.sha(path)
        self.save_manifest(manifest)

    def test_populated_inventory_and_missing_slots_are_separate(self):
        manifest = offline.verify(self.root)
        self.assertEqual(len(manifest["cases"]), 18)
        self.assertEqual(len(manifest["provisional_slots"]), 12)
        self.assertEqual(manifest["inventory"]["substantive_bugs"], 6)
        self.assertFalse(manifest["split_frozen"])

    def test_manifest_and_schema_hash_tampering(self):
        (self.root / "manifest.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Manifest hash"):
            offline.verify(self.root)
        shutil.copyfile(ROOT / "manifest.json", self.root / "manifest.json")
        (self.root / "labels.schema.json").write_text("{}")
        with self.assertRaisesRegex(ValueError, "Artifact hash"):
            offline.verify(self.root)

    def test_each_artifact_is_hash_checked(self):
        manifest = offline.load(ROOT / "manifest.json")
        for kind, ref in manifest["cases"][0]["artifacts"].items():
            with self.subTest(kind=kind):
                path = self.root / ref["path"]
                original = path.read_bytes()
                path.write_bytes(original + b"tampered")
                with self.assertRaisesRegex(ValueError, "Artifact hash"):
                    offline.verify(self.root)
                path.write_bytes(original)

    def test_path_traversal_and_symlink_escape(self):
        manifest = offline.load(self.root / "manifest.json")
        ref = manifest["cases"][0]["artifacts"]["context"]
        outside = self.root.parent / "outside.txt"
        outside.write_text("inert")
        ref.update(path="../outside.txt", sha256=offline.sha(outside))
        self.save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            offline.verify(self.root)
        (self.root / "escape").symlink_to(outside)
        ref["path"] = "escape"
        self.save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "Unsafe"):
            offline.verify(self.root)

    def test_family_leakage_is_rejected(self):
        manifest = offline.load(self.root / "manifest.json")
        manifest["cases"][1]["split"] = "holdout"
        self.save_manifest(manifest)
        with self.assertRaisesRegex(ValueError, "Family leakage"):
            offline.verify(self.root)

    def test_duplicate_cases_slots_and_false_freeze(self):
        original = offline.load(self.root / "manifest.json")
        for mutate in [lambda m: m["cases"].append(m["cases"][0]),
                       lambda m: m["provisional_slots"].append(m["provisional_slots"][0]),
                       lambda m: m.update(split_frozen=True)]:
            manifest = copy.deepcopy(original)
            mutate(manifest)
            self.save_manifest(manifest)
            with self.assertRaises(ValueError):
                offline.verify(self.root)

    def test_schema_strict_fields_versions_shas_and_bool_integers(self):
        original = offline.load(self.root / "manifest.json")
        for mutate in [lambda m: m.update(schema_version=2), lambda m: m.update(schema_version=True),
                       lambda m: m.update(unexpected=True),
                       lambda m: m["cases"][0].update(base_sha="short"),
                       lambda m: m["inventory"].update(substantive_bugs=True)]:
            manifest = copy.deepcopy(original)
            mutate(manifest)
            self.save_manifest(manifest)
            with self.assertRaises(ValueError):
                offline.verify(self.root)
        with self.assertRaisesRegex(ValueError, "Unsupported"):
            offline.schema_check({}, {"$ref": "https://must-not-resolve"})

    def test_duplicate_json_and_nonfinite_values_rejected(self):
        path = self.root / "bad.json"
        for text in ['{"a":1,"a":2}', '{"a":NaN}', '{"a":Infinity}']:
            path.write_text(text)
            with self.assertRaises(ValueError):
                offline.load(path)

    def test_snapshot_and_diff_consistency(self):
        manifest = offline.load(self.root / "manifest.json")
        case = manifest["cases"][0]
        snapshot = offline.load(self.root / case["artifacts"]["snapshot"]["path"])
        snapshot["head_content"] += "# added data\n"
        self.mutate_artifact(manifest, case, "snapshot", snapshot)
        with self.assertRaisesRegex(ValueError, "Snapshot/diff"):
            offline.verify(self.root)

    def test_labels_must_bind_to_changed_line_and_count(self):
        manifest = offline.load(self.root / "manifest.json")
        case = manifest["cases"][0]
        labels = offline.load(self.root / case["artifacts"]["labels"]["path"])
        labels["bugs"][0]["line"] = 999
        self.mutate_artifact(manifest, case, "labels", labels)
        with self.assertRaisesRegex(ValueError, "Invalid bug anchor"):
            offline.verify(self.root)

    def test_clean_case_requires_rationale(self):
        manifest = offline.load(self.root / "manifest.json")
        case = manifest["cases"][1]
        labels = offline.load(self.root / case["artifacts"]["labels"]["path"])
        labels["clean_rationale"] = " "
        self.mutate_artifact(manifest, case, "labels", labels)
        with self.assertRaisesRegex(ValueError, "Missing clean rationale"):
            offline.verify(self.root)

    def test_replay_works_after_labels_are_removed(self):
        shutil.rmtree(self.root / "labels")
        manifest = offline.verify(self.root, with_labels=False)
        result = offline.replay(self.root, manifest)
        self.assertEqual(result["score"]["expectation_mismatches"], 0)
        with self.assertRaises(ValueError):
            offline.verify(self.root)

    def test_actual_runtime_validation_and_payload_are_used(self):
        manifest = offline.verify(self.root)
        with patch.object(runtime, "analyze", wraps=runtime.analyze) as analyze, \
                patch.object(runtime, "parse_response", wraps=runtime.parse_response) as parse, \
                patch.object(runtime.review, "validate_findings", wraps=runtime.review.validate_findings) as validate:
            result = offline.replay(self.root, manifest)
        self.assertEqual(analyze.call_count, 25)
        self.assertGreater(parse.call_count, 20)
        self.assertGreater(validate.call_count, 10)
        self.assertEqual(result["cases"][0]["final_payload"]["commit_id"], build_corpus.HEAD)
        self.assertEqual(len(result["cases"][0]["final_payload"]["comments"]), 1)

    def test_deterministic_no_credentials_network_publish_or_code_execution(self):
        manifest = offline.verify(self.root)
        with patch.dict(os.environ, {"GOOGLE_API_KEY": "must-not-appear", "GEMINI_MODEL": "must-not-appear"}), \
                patch("urllib.request.urlopen", side_effect=AssertionError("network")), \
                patch("subprocess.run", side_effect=AssertionError("execution")), \
                patch.object(runtime, "publish", side_effect=AssertionError("publication")):
            first = offline.replay(self.root, manifest)
            second = offline.replay(self.root, manifest)
        self.assertEqual(first, second)
        self.assertNotIn("must-not-appear", json.dumps(first))

    def test_replay_is_stable_across_host_dates_and_restores_clock(self):
        manifest = offline.verify(self.root)
        real_date = datetime.date
        results = []
        for day in [real_date(2026, 11, 23), real_date(2027, 1, 1)]:
            with patch.object(runtime.review.datetime, "date") as host_date:
                host_date.today.return_value = day
                results.append(offline.replay(self.root, manifest))
                self.assertIs(runtime.review.datetime.date, host_date)
                self.assertEqual(host_date.today(), day)
        self.assertEqual(results[0], results[1])
        self.assertEqual(results[0]["replay_date"], "2026-11-23")
        self.assertIs(runtime.review.datetime.date, real_date)

    def test_failure_partial_duplicate_coverage_and_retry_denominators(self):
        result = offline.replay(self.root, offline.verify(self.root))
        score = result["score"]
        self.assertEqual(score["case_denominator"], 18)
        self.assertEqual(score["attempt_denominator"], 25)
        self.assertEqual(score["statuses"], {"complete-clean": 9, "complete-findings": 7, "failed": 7, "partial": 2})
        self.assertEqual(score["parsed_finding_denominator"], 10)
        self.assertEqual(score["unparseable_called_attempts"], 7)
        for key in ["duplicates", "rejected_findings", "severity_filtered", "coverage_incomplete_attempts"]:
            self.assertEqual(score[key], 1)
        for case in result["cases"]:
            for attempt in case["attempts"]:
                if attempt["record"]["status"] not in runtime.SUCCESS:
                    self.assertIsNone(runtime.MARKER.search(attempt["payload"]["body"]))
                    self.assertNotIn("Code Review — clean", attempt["payload"]["body"])

    def test_thinking_is_charged_once_and_missing_is_not_zero(self):
        attempt = build_corpus.attempt({})
        self.assertEqual(offline.usage_cost(attempt)["usd"], "0.0002")
        attempt["usage"]["state"] = "estimated"
        self.assertEqual(offline.usage_cost(attempt)["state"], "estimated")
        attempt["usage"] = {"state": "missing"}
        self.assertIsNone(offline.usage_cost(attempt)["usd"])
        score = offline.replay(self.root, offline.verify(self.root))["score"]
        self.assertEqual(score["mock_known_usd_subtotal"], "0.0040")
        self.assertIsNone(score["mock_total_usd"])
        self.assertEqual(score["unknown_cost_attempts"], 4)

    def test_invalid_usage_and_rates_fail(self):
        for value in [-1, True, "100", None]:
            attempt = build_corpus.attempt({})
            attempt["usage"]["input_tokens"] = value
            with self.assertRaises(ValueError):
                offline.usage_cost(attempt)
        for rate in ["NaN", "Infinity", "-1"]:
            attempt = build_corpus.attempt({})
            attempt["mock_rates_per_million"]["input"] = rate
            with self.assertRaises(ValueError):
                offline.usage_cost(attempt)

    def test_generator_is_reproducible_and_refuses_overwrite(self):
        generated = self.root.parent / "generated"
        build_corpus.build(generated)
        self.assertEqual(offline.sha(generated / "manifest.json"), offline.sha(ROOT / "manifest.json"))
        offline.verify(generated)
        with self.assertRaises(FileExistsError):
            build_corpus.build(generated)

    def test_cli_exit_output_and_mismatch(self):
        output = self.root.parent / "result.json"
        command = [sys.executable, str(Path(offline.__file__)), "replay", "--corpus", str(self.root), "--output", str(output)]
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 0)
        self.assertEqual(offline.load(output)["score"]["expectation_mismatches"], 0)
        self.assertNotEqual(subprocess.run(command, capture_output=True).returncode, 0)
        original = output.read_bytes()
        manifest = offline.load(self.root / "manifest.json")
        case = manifest["cases"][0]
        fixture = offline.load(self.root / case["artifacts"]["replay"]["path"])
        fixture["attempts"][0]["expected_status"] = "failed"
        self.mutate_artifact(manifest, case, "replay", fixture)
        command[-1] = str(self.root.parent / "mismatch.json")
        self.assertEqual(subprocess.run(command, capture_output=True).returncode, 1)
        self.assertEqual(output.read_bytes(), original)


if __name__ == "__main__":
    unittest.main()
