"""Local JSON fixture replay only. Never calls the production network or publisher.

This is a protocol/accounting screen, not a model-quality evaluator. Fixture code
is data: it is never imported, compiled, or executed.
"""
import argparse
from collections import Counter
from decimal import Decimal
import difflib
import hashlib
import json
from pathlib import Path
import re
from unittest.mock import patch

import runtime


def load(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("Duplicate JSON key")
            result[key] = value
        return result
    return json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=unique,
                      parse_constant=lambda value: (_ for _ in ()).throw(ValueError(value)))


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def require(condition, message):
    if not condition:
        raise ValueError(message)


def schema_check(value, schema, location="root"):
    """Validate the deliberately small JSON Schema subset used by this corpus.

    Unknown schema keywords fail rather than being silently ignored. No remote
    resolution or executable extensions. The schemas are also ordinary draft
    2020-12 documents for use with independent JSON Schema implementations.
    """
    supported = {"$schema", "title", "description", "type", "properties", "required",
                 "additionalProperties", "items", "enum", "const", "pattern",
                 "minimum", "minLength", "minItems"}
    require(not set(schema) - supported, "Unsupported schema keyword")
    types = {"object": dict, "array": list, "string": str, "integer": int,
             "boolean": bool, "null": type(None)}
    if "type" in schema:
        require(type(value) is types[schema["type"]], f"{location}: wrong type")
    if "const" in schema:
        require(type(value) is type(schema["const"]) and value == schema["const"], f"{location}: wrong constant")
    if "enum" in schema:
        require(value in schema["enum"], f"{location}: wrong enum")
    if isinstance(value, dict):
        props = schema.get("properties", {})
        require(set(schema.get("required", [])) <= value.keys(), f"{location}: missing fields")
        if schema.get("additionalProperties") is False:
            require(not value.keys() - props.keys(), f"{location}: unknown fields")
        for key in value.keys() & props.keys():
            schema_check(value[key], props[key], location + "." + key)
    if isinstance(value, list):
        require(len(value) >= schema.get("minItems", 0), f"{location}: too few items")
        if "items" in schema:
            for item in value:
                schema_check(item, schema["items"], location + "[]")
    if isinstance(value, str):
        require(len(value) >= schema.get("minLength", 0), f"{location}: too short")
        if "pattern" in schema:
            require(re.fullmatch(schema["pattern"], value) is not None, f"{location}: pattern")
    if type(value) is int and "minimum" in schema:
        require(value >= schema["minimum"], f"{location}: below minimum")


def artifact(root, ref):
    path = (root / ref["path"]).resolve()
    require(path.is_relative_to(root.resolve()) and path.is_file(), "Unsafe or missing artifact")
    require(sha(path) == ref["sha256"], "Artifact hash mismatch: " + ref["path"])
    return path


def snapshot_files(snapshot):
    """Derive real patch bytes from inert synthetic overlay content."""
    patch_text = "".join(difflib.unified_diff(
        snapshot["base_content"].splitlines(True), snapshot["head_content"].splitlines(True),
        fromfile="a/" + snapshot["file"], tofile="b/" + snapshot["file"], n=3))
    patch_text = "\n".join(patch_text.splitlines()[2:])
    return [{"filename": snapshot["file"], "patch": patch_text,
             "additions": sum(line.startswith("+") for line in patch_text.splitlines()),
             "deletions": sum(line.startswith("-") for line in patch_text.splitlines())}]


def verify(root, with_labels=True):
    manifest_path = root / "manifest.json"
    require(sha(manifest_path) == (root / "manifest.sha256").read_text().strip(), "Manifest hash mismatch")
    manifest = load(manifest_path)
    require(set(manifest["schemas"]) == {"manifest", "labels", "replay"}, "Missing schema binding")
    for name, ref in manifest["schemas"].items():
        require(ref["path"] == name + ".schema.json", "Invalid schema binding")
        artifact(root, ref)
    schema_check(manifest, load(root / "manifest.schema.json"))
    ids, families, counts, splits = set(), {}, Counter(), Counter()
    bugs = 0
    for case in manifest["cases"]:
        require(case["id"] not in ids, "Duplicate case")
        ids.add(case["id"])
        counts[case["category"]] += 1
        splits[case["split"]] += 1
        family = case["family"]
        require(families.setdefault(family, case["split"]) == case["split"], "Family leakage")
        paths = {key: artifact(root, ref) for key, ref in case["artifacts"].items()
                 if key != "labels" or with_labels}
        snapshot = load(paths["snapshot"])
        require(set(snapshot) == {"file", "base_content", "head_content"}, "Invalid snapshot")
        require(all(isinstance(v, str) and v for v in snapshot.values()), "Empty snapshot")
        replay = load(paths["replay"])
        schema_check(replay, load(root / "replay.schema.json"))
        files = snapshot_files(snapshot)
        expected_diff, _ = runtime.reconcile(files, 1, [])
        require(paths["diff"].read_text() == expected_diff, "Snapshot/diff mismatch")
        require(replay["files"] == files or case["category"] == "adversarial", "Replay/snapshot mismatch")
        require(case["provenance"]["kind"] == "synthetic-overlay", "Unimplemented historical verification")
        require(case["provenance"]["access"] == "authorized-repository-and-authored-fixtures", "Unverified access")
        require(case["provenance"]["redaction"] == "no-private-source-used", "Unverified redaction")
        if with_labels:
            labels = load(paths["labels"])
            schema_check(labels, load(root / "labels.schema.json"))
            require(labels["case_id"] == case["id"], "Label binding mismatch")
            bug_ids = [bug["id"] for bug in labels["bugs"]]
            require(len(set(bug_ids)) == len(bug_ids), "Duplicate bug label")
            ranges = runtime.review.parse_diff_ranges(expected_diff)
            for bug in labels["bugs"]:
                require(bug["file"] == snapshot["file"] and any(
                    lo <= bug["line"] <= hi for lo, hi in ranges.get(bug["file"], [])), "Invalid bug anchor")
            require(bool(labels["bugs"]) or bool(labels["clean_rationale"].strip()), "Missing clean rationale")
            require(case["category"] != "clean" or not labels["bugs"], "Clean case has bugs")
            bugs += len(labels["bugs"])
    require(all(counts[key] == value for key, value in manifest["inventory"]["populated"].items()), "Inventory mismatch")
    require(not with_labels or bugs == manifest["inventory"]["substantive_bugs"], "Bug count mismatch")
    missing, missing_splits = Counter(), Counter()
    for slot in manifest["provisional_slots"]:
        require(slot["id"] not in ids, "Duplicate slot")
        ids.add(slot["id"])
        missing[slot["category"]] += 1
        missing_splits[slot["split"]] += 1
    for category, target in manifest["inventory"]["target"].items():
        require(counts[category] + missing[category] == target, "Target/slot mismatch")
    require(splits["development"] + missing_splits["development"] == 10, "Development slot mismatch")
    require(splits["holdout"] + missing_splits["holdout"] == 20, "Holdout slot mismatch")
    require(not manifest["split_frozen"], "Incomplete inventory cannot claim freeze")
    return manifest


def usage_cost(attempt):
    """Mock USD rates; output rate includes separate thinking tokens exactly once.

    Missing fields are unknown, not zero. Report known subtotal separately from
    total; measured describes fixture usage provenance, never real spend.
    """
    usage = attempt["usage"]
    state = usage["state"]
    if state == "missing":
        return {"state": state, "usd": None}
    keys = ("input_tokens", "output_tokens", "thinking_tokens")
    if any(type(usage.get(k)) is not int or usage[k] < 0 for k in keys):
        raise ValueError("Incomplete/invalid usage must be marked missing")
    rates = attempt["mock_rates_per_million"]
    values = [Decimal(rates[k]) for k in ("input", "output_including_thinking")]
    require(all(v.is_finite() and v >= 0 for v in values), "Invalid mock rate")
    cost = (usage[keys[0]] * values[0] + (usage[keys[1]] + usage[keys[2]]) * values[1]) / Decimal(1000000)
    return {"state": state, "usd": str(cost), **{k: usage[k] for k in keys}}


def replay_case(root, case):
    fixture = load(artifact(root, case["artifacts"]["replay"]))
    env = {"GITHUB_REPOSITORY": "offline/fixture", "PR_NUMBER": "1", "EXCLUDE_PATHS": "none"}
    # Not os.environ: credentials, user prompts, fragments and model overrides
    # cannot leak into replay. Both forbidden production boundaries fail closed.
    def forbidden(*args, **kwargs):
        raise AssertionError("Network/publication forbidden in offline replay")

    diff, coverage = runtime.reconcile(fixture["files"], fixture["expected_files"], [])
    record = {"version": runtime.VERSION, "repo": "offline/fixture", "pr": 1,
              "head": case["head_sha"], "base": case["base_sha"], "tool": runtime.tool_identity(),
              "coverage": coverage, "scope": "full", "scope_reason": "offline-synthetic-overlay",
              "previous_head": None, "diff_sha256": runtime.digest(diff),
              "files_sha256": runtime.digest(fixture["files"])}
    results = []
    with patch.object(runtime, "request_model", forbidden), patch.object(runtime, "gh", forbidden), \
            patch.object(runtime, "publish", forbidden), patch("urllib.request.urlopen", forbidden):
        for index, attempt in enumerate(fixture["attempts"]):
            calls = []
            def mock_model(prompt, model, config, api_key):
                require(api_key == "", "Credential reached mock")
                calls.append(True)
                if attempt["error"]:
                    raise RuntimeError("Recorded mock transport failure")
                return attempt["response"]
            payload, outcome = runtime.analyze(diff, record, env, model_call=mock_model, fragments=())
            parsed_count = None
            if calls and not attempt["error"]:
                try:
                    parsed_count = len(runtime.parse_response(attempt["response"])["findings"])
                except Exception:
                    pass
            cost = usage_cost(attempt) if calls else {"state": "not-called", "usd": "0"}
            results.append({"attempt": index + 1, "model_called": bool(calls),
                            "parsed_findings": parsed_count, "usage": cost,
                            "expectation_met": outcome["status"] == attempt["expected_status"],
                            "record": outcome, "payload": payload})
    return {"case_id": case["id"], "family": case["family"], "split": case["split"],
            "attempts": results, "final_payload": results[-1]["payload"]}


def replay(root, manifest):
    cases = [replay_case(root, case) for case in manifest["cases"]]
    attempts = [a for case in cases for a in case["attempts"]]
    audits = [a["record"]["audit"] for a in attempts]
    unknown_cost = sum(a["usage"]["usd"] is None for a in attempts)
    subtotal = sum((Decimal(a["usage"]["usd"]) for a in attempts if a["usage"]["usd"] is not None), Decimal(0))
    return {"schema_version": 1, "qualification": "scripted-protocol-screen-not-model-quality",
            "manifest_sha256": sha(root / "manifest.json"), "cases": cases,
            "score": {"case_denominator": len(cases), "attempt_denominator": len(attempts),
                      "substantive_bug_denominator": manifest["inventory"]["substantive_bugs"],
                      "statuses": dict(Counter(a["record"]["status"] for a in attempts)),
                      "expectation_mismatches": sum(not a["expectation_met"] for a in attempts),
                      "parsed_finding_denominator": sum(a["parsed_findings"] or 0 for a in attempts),
                      "unparseable_called_attempts": sum(a["model_called"] and a["parsed_findings"] is None for a in attempts),
                      "rejected_findings": sum(len(a["rejected"]) for a in audits),
                      "duplicates": sum(a["duplicates"] for a in audits),
                      "severity_filtered": sum(a["severity_filtered"] for a in audits),
                      "coverage_incomplete_attempts": sum(not a["record"]["coverage"]["complete"] for a in attempts),
                      "usage_states": dict(Counter(a["usage"]["state"] for a in attempts)),
                      "mock_known_usd_subtotal": str(subtotal), "unknown_cost_attempts": unknown_cost,
                      "mock_total_usd": None if unknown_cost else str(subtotal)}}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["verify", "replay"])
    parser.add_argument("--corpus", type=Path, default=Path(__file__).parent / "corpus")
    parser.add_argument("--without-labels", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    manifest = verify(args.corpus, with_labels=not args.without_labels)
    result = replay(args.corpus, manifest) if args.command == "replay" else {
        "manifest_sha256": sha(args.corpus / "manifest.json"), "inventory": manifest["inventory"],
        "split_frozen": manifest["split_frozen"], "labels_verified": not args.without_labels}
    text = json.dumps(result, sort_keys=True, indent=2) + "\n"
    if args.output:
        # Exclusive creation: do not overwrite user evidence or corpus artifacts.
        with args.output.open("x", encoding="utf-8") as output:
            output.write(text)
    else:
        print(text, end="")
    if args.command == "replay" and result["score"]["expectation_mismatches"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
