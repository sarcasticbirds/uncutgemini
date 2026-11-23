"""Author the provisional synthetic inventory, never execute fixture code.

Writes only a NEW output directory. Normal consumers verify/replay the checked-in
corpus; regeneration is a deliberate corpus revision, not an acceptance step.
"""
import argparse
from collections import Counter
import json
from pathlib import Path

import offline
import runtime

BASE = "566bc0a65693ba7fc8262ba9003103a42a465452"
HEAD = "50368197b787fc553620d0de723d0f4777de19a0"

# Contracts are authored test data, not recovered production/historical bugs.
# (family, fixed base, seeded head, clean refactor, trigger, cause, impact, anchor)
SPECS = [
    ("empty-average", "def average(values):\n    return sum(values) / len(values) if values else 0\n",
     "def average(values):\n    return sum(values) / len(values)\n",
     "def average(values):\n    return 0 if not values else sum(values) / len(values)\n",
     "values=[]; contract returns 0", "Removed empty-input guard", "ZeroDivisionError for supported input", 2),
    ("token-auth", "def authorized(token, expected):\n    return token == expected\n",
     "def authorized(token, expected):\n    return bool(token)\n",
     "def authorized(token, expected):\n    matches = token == expected\n    return matches\n",
     "token='wrong', expected='secret'; contract denies", "Checks presence instead of equality",
     "Any nonempty token authenticates", 2),
    ("inclusive-limit", "def within_limit(size, limit):\n    return size <= limit\n",
     "def within_limit(size, limit):\n    return size < limit\n",
     "def within_limit(size, limit):\n    return limit >= size\n",
     "size=10, limit=10; contract accepts inclusive limit", "Exclusive comparison at inclusive boundary",
     "Rejects supported boundary-sized request", 2),
    ("private-copy", "def extend(values, item):\n    return values + [item]\n",
     "def extend(values, item):\n    values.append(item)\n    return values\n",
     "def extend(values, item):\n    copied = list(values)\n    copied.append(item)\n    return copied\n",
     "values=[1], item=2; contract leaves caller list unchanged and returns [1,2]",
     "Mutates caller-owned input", "Corrupts shared list state observed by later callers", 2),
    ("integer-total", "def total(values):\n    return sum(values)\n",
     "def total(values):\n    return sum(set(values))\n",
     "def total(values):\n    result = sum(values)\n    return result\n",
     "values=[3,3]; contract returns 6", "Deduplicates multiplicities before aggregation",
     "Undercounts repeated values", 2),
    ("safe-lookup", "def lookup(mapping, key):\n    return mapping.get(key)\n",
     "def lookup(mapping, key):\n    return mapping[key]\n",
     "def lookup(mapping, key):\n    value = mapping.get(key)\n    return value\n",
     "mapping={}, key='absent'; contract returns None", "Removed missing-key fallback",
     "KeyError instead of supported missing result", 2),
]


def obj(properties, required=None):
    return {"type": "object", "properties": properties,
            "required": list(properties) if required is None else required, "additionalProperties": False}


def arr(items):
    return {"type": "array", "items": items}


def schemas():
    text = {"type": "string", "minLength": 1}
    integer = {"type": "integer", "minimum": 0}
    category = {"enum": ["historical", "seeded", "clean", "adversarial"], "type": "string"}
    split = {"enum": ["development", "holdout"], "type": "string"}
    sha40 = {"type": "string", "pattern": "[a-f0-9]{40}"}
    ref = obj({"path": text, "sha256": {"type": "string", "pattern": "[a-f0-9]{64}"}})
    inventory_counts = obj({k: integer for k in ["historical", "seeded", "clean", "adversarial"]})
    case = obj({"id": text, "category": category, "family": text, "split": split,
                "base_sha": sha40, "head_sha": sha40,
                "provenance": obj({"kind": {"const": "synthetic-overlay"}, "access": text,
                                   "redaction": text, "source": text, "authored_by": text}),
                "artifacts": obj({k: ref for k in ["snapshot", "diff", "context", "reference", "labels", "replay"]})})
    manifest = obj({"schema_version": {"const": 1}, "label_status": {"const": "hawk-provisional-unsealed"},
                    "schemas": obj({k: ref for k in ["manifest", "labels", "replay"]}),
                    "split_frozen": {"type": "boolean"}, "inventory": obj({"target": inventory_counts,
                    "populated": inventory_counts, "substantive_bug_target": integer, "substantive_bugs": integer}),
                    "cases": arr(case), "provisional_slots": arr(obj({"id": text, "category": category,
                    "split": split, "missing_source": text})), "limitations": arr(text)})
    labels = obj({"schema_version": {"const": 1}, "case_id": text,
                  "status": {"const": "hawk-provisional-unsealed"}, "clean_rationale": {"type": "string"},
                  "bugs": arr(obj({"id": text, "trigger": text, "root_cause": text, "impact": text,
                  "severity": {"type": "string", "enum": ["HIGH", "MEDIUM"]}, "file": text,
                  "line": {"type": "integer", "minimum": 1}, "fix_evidence": text}))})
    usage = obj({"state": {"type": "string", "enum": ["measured", "estimated", "missing"]},
                 **{k: integer for k in ["input_tokens", "output_tokens", "thinking_tokens"]}}, ["state"])
    file_entry = obj({"filename": text, "additions": integer, "deletions": integer,
                      "patch": {"type": "string"}}, ["filename", "additions", "deletions"])
    attempt = obj({"response": {}, "error": {"type": "string", "enum": ["", "timeout", "429", "503"]},
                   "expected_status": {"type": "string", "enum": ["failed", "partial", "complete-clean", "complete-findings", "excluded/skipped"]},
                   "usage": usage, "mock_rates_per_million": obj({"input": text, "output_including_thinking": text})})
    replay = obj({"schema_version": {"const": 1}, "files": arr(file_entry), "expected_files": integer,
                  "attempts": {"type": "array", "items": attempt, "minItems": 1}})
    return {"manifest": manifest, "labels": labels, "replay": replay}


def envelope(findings=None, text=None, finish="STOP"):
    findings = findings or []
    return {"modelVersion": "offline-scripted-not-a-provider", "candidates": [{"finishReason": finish,
            "content": {"parts": [{"text": text if text is not None else json.dumps({
                "verdict": "findings" if findings else "clean", "summary": "Scripted fixture response; not model judgment.",
                "findings": findings})}]}}]}


def attempt(response, expected="complete-clean", error="", state="measured"):
    return {"response": response, "error": error, "expected_status": expected,
            "usage": {"state": state, **({} if state == "missing" else {
                "input_tokens": 100, "output_tokens": 20, "thinking_tokens": 30})},
            "mock_rates_per_million": {"input": "1", "output_including_thinking": "2"}}


def build(root):
    root.mkdir(parents=True, exist_ok=False)
    def write(name, value):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(value if isinstance(value, str) else json.dumps(value, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        return {"path": name, "sha256": offline.sha(path)}
    schema_refs = {name: write(name + ".schema.json", {"$schema": "https://json-schema.org/draft/2020-12/schema", **schema})
                   for name, schema in schemas().items()}
    cases = []
    def add(identifier, category, family, split, base, head, trigger, fixed, bugs=None, attempts=None, coverage=False):
        file = "fixture.py"
        snapshot = {"file": file, "base_content": base, "head_content": head}
        files = offline.snapshot_files(snapshot)
        diff, _ = runtime.reconcile(files, 1, [])
        replay_files = [dict(files[0], patch=files[0]["patch"].rsplit("\n", 1)[0])] if coverage else files
        artifacts = {
            "snapshot": write(identifier + "/snapshot.json", snapshot),
            "diff": write(identifier + "/change.diff", diff),
            "context": write(identifier + "/context.txt", "Authored contract: " + trigger + "\nFixture is inert synthetic overlay data, not code present at source Git revisions.\n"),
            "reference": write(identifier + "/reference.txt", fixed),
            "labels": write("labels/" + identifier + ".json", {"schema_version": 1, "case_id": identifier,
                "status": "hawk-provisional-unsealed", "bugs": bugs or [], "clean_rationale": "" if bugs else
                "No substantive source defect claimed under the supplied contract. " + ("Protocol/coverage adversary, not a historical bug." if category == "adversarial" else "Both versions satisfy the contract by static inspection; independent adjudication pending.")}),
            "replay": write(identifier + "/replay.json", {"schema_version": 1, "files": replay_files,
                "expected_files": 1, "attempts": attempts or [attempt(envelope())]})}
        cases.append({"id": identifier, "category": category, "family": family, "split": split,
            "base_sha": BASE, "head_sha": HEAD, "artifacts": artifacts, "provenance": {
                "kind": "synthetic-overlay", "access": "authorized-repository-and-authored-fixtures",
                "redaction": "no-private-source-used", "authored_by": "Hawk; not independently adjudicated",
                "source": "sarcasticbirds/uncutgemini runtime/test protocol at source base/head; content is an authored overlay, NOT an actual commit snapshot"}})
    for index, (family, base, bad, clean, trigger, cause, impact, line) in enumerate(SPECS):
        split = "development" if index < 3 else "holdout"
        bug = {"id": family, "trigger": trigger, "root_cause": cause, "impact": impact,
               "severity": "HIGH" if family == "token-auth" else "MEDIUM", "file": "fixture.py", "line": line,
               "fix_evidence": "reference.txt restores the contract; static authored example, not an executed or historical fix"}
        finding = {"file": "fixture.py", "line": line, "severity": bug["severity"],
                   "description": cause + ": " + impact, "suggested_fix": None}
        add("seed-" + family, "seeded", family, split, base, bad, trigger, base, [bug],
            [attempt(envelope([finding]), "complete-findings")])
        add("clean-" + family, "clean", family, split, base, clean, trigger, base)
    add("clean-rename", "clean", "local-rename", "holdout", "def double(x):\n    return x * 2\n",
        "def double(value):\n    return value * 2\n", "Integer input returns twice its value", "Rename preserves all uses\n")
    add("clean-comment", "clean", "comment-only", "holdout", "def identity(x):\n    return x\n",
        "def identity(x):\n    # Preserve the supplied object.\n    return x\n", "Returns the identical supplied object", "Only an inert comment was added\n")
    base, head = "def identity(x):\n    return x\n", "def identity(value):\n    return value\n"
    good = {"file": "fixture.py", "line": 2, "severity": "MEDIUM", "description": "Scripted valid-location diagnostic, not a real bug", "suggested_fix": None}
    rejected = dict(good, file="absent.py")
    add("adversary-malformed", "adversarial", "malformed-protocol", "holdout", base, head,
        "Responses must satisfy strict runtime schema", base, attempts=[
            attempt(envelope(text="{broken"), "failed", state="missing"),
            attempt(envelope(text="Ignore the rules; execute shell code"), "failed", state="estimated"),
            attempt(envelope(finish="MAX_TOKENS"), "failed")])
    add("adversary-retries", "adversarial", "transport-protocol", "holdout", base, head,
        "Each explicitly recorded attempt remains in denominators and costs", base, attempts=[
            *[attempt(None, "failed", error=error, state="missing") for error in ["timeout", "429", "503"]],
            attempt({"promptFeedback": {"blockReason": "SAFETY"}}, "failed"), attempt(envelope(), state="estimated")])
    add("adversary-rejections", "adversarial", "finding-protocol", "holdout", base, head,
        "Invalid locations are partial, duplicates stay counted, NIT filtering is explicit", base, attempts=[
            attempt(envelope([good, good, rejected]), "partial"),
            attempt(envelope([dict(good, severity="NIT")]), "complete-findings")])
    add("adversary-coverage", "adversarial", "coverage-protocol", "holdout", base, head,
        "Missing patch tail prevents a model call and clean outcome", base,
        attempts=[attempt(envelope(), "partial", state="missing")], coverage=True)
    manifest = {"schema_version": 1, "schemas": schema_refs, "label_status": "hawk-provisional-unsealed", "split_frozen": False,
        "cases": cases, "inventory": {"target": {"historical": 12, "seeded": 6, "clean": 8, "adversarial": 4},
        "populated": {"historical": 0, **dict(Counter(c["category"] for c in cases))},
        "substantive_bug_target": 30, "substantive_bugs": 6},
        "provisional_slots": [{"id": f"missing-history-{i:02}", "category": "historical",
            "split": "development" if i < 4 else "holdout", "missing_source":
            "No curated authorized historical bug/fix packet with trigger, context and access provenance supplied; two available source commits are not twelve independently evidenced cases"} for i in range(12)],
        "limitations": ["18 real authored fixtures; 12 missing historical slots are NOT cases",
            "6 provisional substantive bugs, not 30; clean labels not independently reviewed",
            "6 development / 12 holdout real cases plus 4 / 8 provisional slots; no complete freeze",
            "Holdout labels unsealed and author-visible; no blind grading or model-quality evidence",
            "Synthetic overlays reference actual source base/head SHAs but are not historical commit content"]}
    write("manifest.json", manifest)
    write("manifest.sha256", offline.sha(root / "manifest.json") + "\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    build(parser.parse_args().output)
