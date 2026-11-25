"""Shared, fail-closed review lifecycle. Standard library only.

All network boundaries are injectable for offline regression tests. A full PR
review is intentional: compare API file limits and uncertain ancestry must not
silently turn an incremental optimization into a coverage claim.
"""
import base64
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import urllib.error
import urllib.request

import review

VERSION = 1
SUCCESS = {"complete-clean", "complete-findings"}
MARKER = re.compile(r"\n<!-- uncutgemini:v1:([A-Za-z0-9_=+-]+) -->\Z")


def digest(value):
    if not isinstance(value, str):
        value = json.dumps(value, sort_keys=True, ensure_ascii=True)
    return hashlib.sha256(value.encode()).hexdigest()


def tool_identity():
    return digest([Path(__file__).read_text(), Path(review.__file__).read_text()])


def gh(endpoint, payload=None):
    if payload is not None:
        raise RuntimeError("GitHub writes disabled: no durable cross-job publication coordinator")
    args = ["gh", "api", endpoint]
    result = subprocess.run(args, capture_output=True, text=True, timeout=120)
    if result.returncode:
        # Do not echo server bodies or commands containing user-provided data.
        raise RuntimeError("GitHub request failed; do not replay an uncertain write")
    return json.loads(result.stdout)


def pages(api, endpoint):
    output = []
    for page in range(1, 102):
        batch = api(f"{endpoint}?per_page=100&page={page}")
        if not isinstance(batch, list):
            raise ValueError("Invalid paginated response")
        output.extend(batch)
        if len(batch) < 100:
            return output
    raise ValueError("Pagination bound exceeded")


def exclusions(env):
    value = env.get("EXCLUDE_PATHS", "").strip()
    return ([] if value.lower() == "none" else
            [p.strip() for p in value.split(",") if p.strip()] if value else review.DEFAULT_EXCLUDE_PATHS)


def checkpoint(reviews, repo, number, tool):
    valid = []
    for item in reviews:
        if (item.get("user", {}).get("login") != "github-actions[bot]"
                or item.get("user", {}).get("type") != "Bot"
                or item.get("state") != "COMMENTED"):
            continue
        match = MARKER.search(item.get("body") or "")
        if not match:
            continue
        try:
            record = json.loads(base64.urlsafe_b64decode(match[1]))
            if (record["version"] == VERSION and record["status"] in SUCCESS
                    and record["repo"] == repo and record["pr"] == number
                    and record["head"] == item.get("commit_id") and record["tool"] == tool
                    and record["coverage"]["complete"] is True
                    and not record["coverage"]["omitted"] and not record["audit"]["rejected"]):
                valid.append((item.get("id", 0), record))
        except (ValueError, KeyError, TypeError):
            continue
    return max(valid, default=(0, None), key=lambda pair: pair[0])[1]


def patch_complete(patch, additions, deletions):
    """Check both hunk structure and API line totals to detect missing tails."""
    old_left = new_left = added = removed = 0
    saw_hunk = False
    for line in patch.splitlines():
        if line.startswith("@@"):
            if old_left or new_left:
                return False
            match = re.match(r"^@@ -(\d+)(?:,(\d+))? \+(\d+)(?:,(\d+))? @@", line)
            if not match:
                return False
            old_left = int(match[2]) if match[2] is not None else 1
            new_left = int(match[4]) if match[4] is not None else 1
            saw_hunk = True
        elif line.startswith("\\ No newline at end of file"):
            continue
        elif saw_hunk:
            if line.startswith("+"):
                new_left -= 1
                added += 1
            elif line.startswith("-"):
                old_left -= 1
                removed += 1
            elif line.startswith(" "):
                old_left -= 1
                new_left -= 1
            else:
                return False
            if old_left < 0 or new_left < 0:
                return False
        else:
            return False
    return saw_hunk and old_left == new_left == 0 and added == additions and removed == deletions


def reconcile(files, expected, patterns):
    coverage = {"expected": expected, "included": [], "excluded": [], "omitted": [], "complete": False}
    blocks, seen = [], set()
    for item in files:
        path = item["filename"]
        if path in seen:
            raise ValueError("Duplicate file in pagination")
        seen.add(path)
        if any(review.fnmatch.fnmatch(path, p) or review.fnmatch.fnmatch(path.rsplit("/", 1)[-1], p) for p in patterns):
            coverage["excluded"].append(path)
            continue
        patch = item.get("patch")
        if not isinstance(patch, str) or not patch_complete(patch, item["additions"], item["deletions"]):
            coverage["omitted"].append({"file": path, "reason": "missing-binary-or-incomplete-patch"})
            continue
        old = item.get("previous_filename", path)
        # JSON ASCII quoting is a subset of Git quoting except Unicode escapes;
        # use raw UTF-8 inside quoted paths, preserving spaces and control chars.
        a, b = json.dumps("a/" + old, ensure_ascii=False), json.dumps("b/" + path, ensure_ascii=False)
        blocks.append(f"diff --git {a} {b}\n{patch}\n")
        coverage["included"].append(path)
    coverage["received"] = len(files)
    coverage["complete"] = len(files) == expected and not coverage["omitted"]
    return "".join(blocks), coverage


def prepare(api, env):
    repo, number = env["GITHUB_REPOSITORY"], int(env["PR_NUMBER"])
    endpoint = f"repos/{repo}/pulls/{number}"
    before = api(endpoint)
    head, base = before["head"]["sha"], before["base"]["sha"]
    expected_head = env.get("UG_HEAD_SHA")
    if expected_head and head != expected_head:
        raise ValueError("PR head moved before collection")
    files = pages(api, endpoint + "/files")
    reviews = pages(api, endpoint + "/reviews")
    after = api(endpoint)
    if (after["head"]["sha"], after["base"]["sha"], after["changed_files"]) != (head, base, before["changed_files"]):
        raise ValueError("PR changed during collection")
    diff, coverage = reconcile(files, before["changed_files"], exclusions(env))
    tool = tool_identity()
    prior = checkpoint(reviews, repo, number, tool)
    record = {"version": VERSION, "repo": repo, "pr": number, "head": head, "base": base,
              "tool": tool, "coverage": coverage, "scope": "full",
              "scope_reason": "full-review-safe-fallback", "previous_head": prior["head"] if prior else None,
              "diff_sha256": digest(diff), "files_sha256": digest(files)}
    return diff, record


def request_model(prompt, model, config, api_key):
    if not api_key:
        raise ValueError("Missing model API key")
    payload = {"contents": [{"parts": [{"text": prompt}]}], "generationConfig": config}
    request = urllib.request.Request(
        f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent",
        data=json.dumps(payload).encode(), headers={"Content-Type": "application/json", "x-goog-api-key": api_key})
    # One bounded request. Read failures never trigger repeated paid calls.
    with urllib.request.urlopen(request, timeout=review.GEMINI_TIMEOUT_SECONDS) as response:
        return json.loads(response.read())


def parse_response(data):
    if not isinstance(data, dict) or "error" in data or data.get("promptFeedback", {}).get("blockReason"):
        raise ValueError("Model response failed or blocked")
    candidates = data.get("candidates")
    if not isinstance(candidates, list) or len(candidates) != 1 or candidates[0].get("finishReason") != "STOP":
        raise ValueError("Model did not finish successfully")
    if any(rating.get("blocked") for rating in candidates[0].get("safetyRatings", [])):
        raise ValueError("Model candidate was blocked")
    parts = candidates[0]["content"]["parts"]
    text = "".join(p["text"] for p in parts if not p.get("thought"))
    def unique_object(pairs):
        value = {}
        for key, item in pairs:
            if key in value:
                raise ValueError("Duplicate JSON field")
            value[key] = item
        return value

    result = json.loads(text, object_pairs_hook=unique_object)
    if not isinstance(result, dict) or set(result) != {"verdict", "summary", "findings"}:
        raise ValueError("Invalid response schema")
    if not isinstance(result["summary"], str) or not result["summary"].strip() or not isinstance(result["findings"], list):
        raise ValueError("Invalid summary or findings")
    if result["verdict"] not in ("clean", "findings") or (result["verdict"] == "clean") != (len(result["findings"]) == 0):
        raise ValueError("Inconsistent verdict")
    return result


def analyze(diff, record, env, model_call=request_model, fragments=(), input_sink=None):
    record = json.loads(json.dumps(record))
    model = env.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
    severity = env.get("MIN_SEVERITY", "MEDIUM").upper()
    custom = env.get("CUSTOM_PROMPT", "").strip()
    guidelines = env.get("REVIEW_GUIDELINES", "")
    extra = env.get("EXTRA_INSTRUCTIONS", "")
    # Only scan the original template. Inserted source and instructions are opaque.
    values = {"diff": diff, "guidelines": guidelines, "schema": review.SCHEMA_INSTRUCTIONS}
    prompt = (re.sub(r"\{(diff|guidelines|schema)\}", lambda match: values[match[1]], custom)
              if custom else review.build_prompt(diff, guidelines, extra))
    config = review.build_generation_config(model, len(diff.splitlines()))
    record.update({"model": model, "prompt_sha256": digest(prompt), "generation_config": config,
                   "config_sha256": digest({"model": model, "severity": severity, "custom": custom,
                                            "guidelines": guidelines, "extra": extra, "exclude": exclusions(env)}),
                   "audit": {"rejected": [], "duplicates": 0, "severity_filtered": 0}})
    if input_sink:
        input_sink(record, {"model": model, "prompt": prompt, "generation_config": config})
    findings, summary, status = [], "", "failed"
    try:
        if severity not in review.SEVERITY_RANK:
            raise ValueError("Invalid minimum severity")
        if custom and "{diff}" not in custom:
            raise ValueError("Custom prompt must include {diff}")
        if record["diff_sha256"] != digest(diff) or (diff and diff not in prompt):
            raise ValueError("Review input differs from collected/submitted bytes")
        if not record["coverage"]["complete"]:
            status, summary = "partial", "File coverage is incomplete; no clean conclusion or success checkpoint."
        elif not record["coverage"]["included"]:
            status, summary = "excluded/skipped", "No reviewable patches; no clean conclusion or success checkpoint."
        else:
            record["submitted_diff_sha256"] = digest(diff)
            data = model_call(prompt, model, config, env.get("GOOGLE_API_KEY", ""))
            record["response_sha256"] = digest(data)
            record["reported_model_version"] = data.get("modelVersion") if isinstance(data, dict) else None
            result = parse_response(data)
            findings = review.validate_findings(result["findings"], review.parse_diff_ranges(diff), record["audit"])
            status = "partial" if record["audit"]["rejected"] else "complete-findings" if findings else "complete-clean"
            summary = result["summary"]
            visible = [f for f in findings if review.SEVERITY_RANK[f["severity"]] <= review.SEVERITY_RANK[severity]]
            record["audit"]["severity_filtered"] = len(findings) - len(visible)
            findings = visible
    except Exception as exc:
        # Provider errors can echo secrets or prompt content: report class only.
        status, summary, findings = "failed", f"Review did not complete ({type(exc).__name__}).", []
    record["status"] = status
    if status in SUCCESS:
        payload = review.build_review_payload(findings, summary, False, "", fragments, diff)
        if status == "complete-findings" and not findings:
            payload["body"] = payload["body"].replace("Code Review — clean", "Code Review — findings below severity threshold")
            payload["body"] = payload["body"].split("\n---\n")[0]
    else:
        payload = review.build_failure_payload(summary, False, "", fragments, diff)
        payload["body"] = payload["body"].replace("Code Review — failed", f"Code Review — {status}")
        # Valid findings from a partial review remain available, but never clean.
        payload["comments"] = review.build_review_payload(findings, summary, False, "", [], diff)["comments"]
    payload["commit_id"] = record["head"]
    payload["body"] += f"\n\nRuntime outcome: **{status}**\n\n<details><summary>Review provenance and coverage</summary>\n\n```json\n{json.dumps(record, sort_keys=True, indent=2)}\n```\n</details>"
    if status in SUCCESS:
        token = base64.urlsafe_b64encode(json.dumps(record, sort_keys=True).encode()).decode()
        payload["body"] += f"\n<!-- uncutgemini:v1:{token} -->"
    return payload, record


def publication_identity(record):
    # Stable across temporary directories, payload wording and fresh analyses.
    # An identity is NOT a distributed claim or permission to publish.
    return digest({key: record[key] for key in ("repo", "pr", "head", "base")})


def publish(api, payload, record, journal):
    """Fail closed: the provisioned runtime has no cross-job write coordinator.

    Neither a local journal, an env opt-in, Actions concurrency nor a remote
    review-list read can rule out an in-flight/unknown POST from another job.
    There is intentionally no supported POST or automatic recovery path here.
    Existing published/unknown evidence must never be overwritten or replayed.
    """
    if len(payload["body"].encode("utf-8")) > 65000 or len(payload["comments"]) > 100:
        raise ValueError("Review exceeds conservative publication limits; evidence retained without posting")
    try:
        # Exclusive creation protects evidence on this filesystem only; it is
        # not represented as a durable cross-job publication claim.
        with journal.open("x", encoding="utf-8") as output:
            json.dump({"state": "blocked", "reason": "cross-job-coordination-unavailable",
                       "publication_identity": publication_identity(record),
                       "payload_sha256": digest(payload), "success_checkpoint": False}, output)
    except FileExistsError:
        raise RuntimeError("Publication evidence exists; preserved without replay") from None
    raise RuntimeError("Publication disabled: durable cross-job claim/reconciliation unavailable; evidence retained")


def run():
    notice = "Analysis only — publication disabled — not delivered"
    print(notice)
    env = dict(os.environ)
    env["PR_NUMBER"] = env.get("PR_NUMBER") or env["UG_PR_NUMBER"]
    directory = Path(tempfile.mkdtemp(prefix="uncutgemini-", dir=env.get("RUNNER_TEMP")))
    print(f"Runtime evidence directory: {directory}")
    if env.get("GITHUB_ENV"):
        with open(env["GITHUB_ENV"], "a") as output:
            output.write(f"UG_EVIDENCE_DIR={directory}\n")
    diff, record = prepare(gh, env)
    (directory / "input.json").write_text(json.dumps(record, indent=2))
    (directory / "pr.diff").write_text(diff)
    guidelines = env.get("GUIDELINES_FILE", ".github/review-guidelines.md")
    if Path(guidelines).is_file():
        env["REVIEW_GUIDELINES"] = Path(guidelines).read_text()
    def save_input(metadata, request):
        (directory / "input.json").write_text(json.dumps(metadata, indent=2))
        (directory / "request.json").write_text(json.dumps(request, indent=2))

    payload, record = analyze(diff, record, env, fragments=review.read_fragments(), input_sink=save_input)
    (directory / "result.json").write_text(json.dumps(record, indent=2))
    (directory / "payload.json").write_text(json.dumps(payload, indent=2))
    (directory / "delivery.json").write_text(json.dumps({
        "analysis_status": record["status"], "publication_status": "disabled",
        "delivered": False, "success_checkpoint": False,
        "proposed_payload_sha256": digest(payload)}, indent=2))
    if env.get("GITHUB_STEP_SUMMARY"):
        with open(env["GITHUB_STEP_SUMMARY"], "a") as summary:
            summary.write(f"## {notice}\n\n"
                          "Proposed payload follows, not a published review. Any success marker below is prospective only, "
                          "not a delivered checkpoint. A green advisory job proves neither delivery nor complete-clean analysis.\n\n"
                          + payload["body"])
    publish(gh, payload, record, directory / "publication.json")


if __name__ == "__main__":
    run()
