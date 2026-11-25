# Credential-free protocol corpus — provisional v1

This is **not a completed evaluation corpus or model-quality result**. Hawk
authored the fixtures and labels. Robin/Wren reviewed the prior revision with
contract/severity dissent; the corrections below await material-change review.
No independent sealing/grading is claimed. No provider inference, credentials, live posting or fixture-code execution
is required. All scripts use the Python 3.12 standard library.

## Reproduce

From the repository root, using an already installed Python 3.12:

```sh
python3.12 -m unittest -v
python3.12 offline.py verify
python3.12 offline.py replay --without-labels --output replay-one.json
python3.12 offline.py replay --without-labels --output replay-two.json
cmp replay-one.json replay-two.json
```

Output paths must not already exist. Replay exits 1 on any scripted status
mismatch; invalid manifest/schema/hash/split data also exits nonzero. A successful
verification confirms internal integrity, not completeness or label correctness.
The full JSON includes each attempt's actual runtime record and review payload,
and each case's `final_payload` (the last explicitly recorded attempt). It is a
dry-run `COMMENT` payload, never sent to GitHub. Failed and partial payloads have
no success checkpoint. Retry fixtures are explicit ordered data, not automatic
retry policy or a network runner. Nothing imports/executes snapshot code.
The offline harness pins the prompt clock to `2026-11-23` and records
`replay_date`, so prompt hashes and payload bytes remain stable across host dates.
Production prompt dating is unchanged. Recovery found that the original harness
was only same-day deterministic; its saved November 23 evidence predates this fix.

If Python is absent, the implementation guest used locally downloaded uv
**0.13.9** for aarch64 Linux, then `uv python install 3.12.12` and
`uv run --no-project --python 3.12.12 python -m unittest -v`. This is a direct
guest test, not a Flox check. Consumer replay needs neither uv nor network.

## Inventory and provenance

| Category | Real populated fixtures | Target |
|---|---:|---:|
| Authorized historical bug/fix | **0** | 12 |
| Authored seeded defects | 6 | 6 |
| Authored clean/refactor | 8 | 8 |
| Authored adversarial/coverage | 4 | 4 |
| Total | **18** | **30** |

There are **6** provisional substantive bug labels, versus at least **30**
required. Scripted diagnostics in adversarial cases are *not* substantive bugs.
Clean cases have rationales; prior narrow adjudications are preserved in the review records, not extended to these replacement bytes automatically.

Missing source: twelve curated, authorized historical packets with contextual
trigger/root cause/impact, actual bug/fix snapshots, fix evidence and auditable
access/redaction provenance. This bounded checkout initially contained only the
main merge and runtime handoff commits. Those commits alone are not evidence of
twelve historical cases. No external/private repositories were searched and no
historical access or labels were invented. Twenty-four more substantive bugs
are required; filling the twelve slots alone does not guarantee that floor.

Two development-visible [historical candidate packets](../historical-candidates/README.md)
now preserve actual source/fix/introduction bytes, caller paths, hashes, access/license
basis and explicit missing evidence. They are outside the accepted manifest and
scoring; they do not fill slots or increase bug counts. Historical source is inert
and has not been executed, imported or compiled.

## Bounded authored correction

The input at `46d55b90d7cec965bedb7fe4888d5a35f3d587e6` changed ordinary
`double(x)` to `double(value)` and similarly renamed identity parameters in four
protocol overlays. That broke `x=` binding; the old clean claim is not universally
valid. The replacement keeps parameter `x`, adds local `value = x`, and uses
that local in the return. Positional and keyword contracts are explicit; static
AST/signature-binding regressions check both without running fixture source.
Protocol families, grouping and scripted diagnostic intent are unchanged.

The five non-auth seeded severities change from MEDIUM to HIGH for supported
wrong-result/crash/data-integrity impacts under the existing runtime rubric;
token-auth stays HIGH. Six substantive seeded bugs remain six. Production rubric,
model defaults and independent review records are unchanged. Exact old/new hashes
are delivered with the correction task evidence; hashes prove bytes, not grading
independence. The old answer-exposed split remains unsealed/unfrozen, not fresh.

Every populated case is explicitly a **synthetic overlay**, not a historical
Git snapshot. Full source base/head SHAs identify the authorized repository
versions from which the runtime/fixture protocol was taken; **they do not claim
that the authored Python snippets existed at those commits**. The actual overlay
base/head content, derived diff, contract context, reference and labels each have
SHA-256 hashes. `reference.txt` is authored static fix/behavior evidence, not an
executed fix or independently established historical cause. New fixture content
contains no private source; this is not a claim of a redaction audit of private
material.

## Integrity and split

`manifest.json` v1 binds schema and artifact hashes. `manifest.sha256` binds its
bytes; the immutable Git commit is the external trust anchor (not this mutable
sidecar by itself). `offline.py verify` checks the versioned draft-2020-12 JSON
schemas using a documented restricted, fail-closed standard-library validator,
all artifact bytes, snapshot/diff consistency, non-adversarial replay inputs,
changed-line label anchors, rationales, inventory, duplicate IDs and family
leakage. It rejects unknown schema keywords and never resolves remote schemas.
Adversarial replay inputs intentionally deviate from intact source snapshots to
exercise coverage failure; their separate replay bytes are hashed too.

Real allocation is **6 development / 12 holdout**. Missing historical slots are
separately **4 development / 8 holdout**, for provisional capacities of 10/20.
Each seeded defect and its clean sibling stay in the same family/split.
`split_frozen` is false: this is **not a complete freeze**. Historical families
must be reconciled before a real freeze; no author-visible holdout is blind.

Per-case label artifacts live in `corpus/labels/`; `--without-labels` neither
opens nor requires them (the aggregate bug denominator remains public metadata).
The authoring generator embeds label specifications, and reference/context files
also reveal expected behavior. Removing the label directory alone is not blinding.
This permits a later Wren-controlled label store, but does not itself seal
anything. Default verification includes labels. Do not edit/delete source labels
to claim blinding; Wren must independently adjudicate, control and document the
future seal and grading boundary, including isolation of authoring/reference data.

`build_corpus.py NEW_DIRECTORY` deterministically regenerates the authored v1
data and refuses an existing directory. Do not regenerate/relabel fixtures to
make a failing candidate pass. A material corpus change needs a new immutable
handoff and review, not just a rewritten checksum.

## Scoring and mock costs

The scoring ledger counts **all 18 cases and 25 attempts**, not just successes:
9 complete-clean, 7 complete-findings, 7 failed, 2 partial; one incomplete
coverage attempt never invokes the mock model. It retains 10 parsed submitted
findings including one rejected finding, one duplicate and one severity-filtered
finding, plus 7 unparseable/failed called attempts as separate unknown-output
denominators. An unreadable response is not reported as zero submitted findings.
Attempt findings are not unique-bug counts. There is no semantic matching,
precision/recall, automatic label adjudication or model ranking.

Each recorded call has mock usage with `measured`, `estimated` or `missing`
provenance. Here even “measured” is **scripted usage, not real provider evidence**.
Rates are intentionally illustrative, not a current provider price quote.
The explicit convention is completion output tokens **excluding** thinking,
plus separate thinking tokens, both charged once at the output/thinking rate.
Every retry is charged separately. Missing usage is unknown, never zero; a
noncalled attempt is separately `not-called` and costs zero. The known mock
subtotal is $0.0040, but the mock total is **unknown** because four called
attempts have missing usage. No inference spend occurred. A future provider
adapter would need to verify its token-field semantics before using this ledger.

## Remaining runtime and acceptance limits

This slice does not modify the production runtime, default model or advisory
behavior. Retained limits: full-PR fallback cost; no durable cross-job replay
lock; residual head-read/POST race; restrictive suggestions; unverified hosted
Actions/provider behavior. Existing runtime regressions are implementation
evidence only. Offline passes do not establish model quality, release readiness,
precision/recall, 99% reliability or the parent's complete-corpus criterion.
Rook owns consuming the exact-SHA handoff and routing independent Robin review
and separate Wren QA/adjudication before any acceptance or correction decision.
