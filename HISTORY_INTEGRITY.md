# Offline historical candidate identity integrity

`history_expectations.json` is a code-owned trust anchor, not packet input.
Changing it requires code review. Verification never learns expectations from
the directory passed to `--verify`; it needs no Git, network, or historical
execution. Success means candidate identity integrity, **not historical admission**.

## Authoring provenance (2026-11-24)

Starting code and packet baseline:
`40a1f2e7d84b0484ac9c5ca8f5e6418fe128ba3e` (draft PR 16).
Using provisioned managed Git on `sarcasticbirds/uncutgemini`:

```
git fetch origin 71c51d8ceabddb7e04dc7f5707a19556f40d7acc 1a59e878ea812907cd9c61e4e2366c6d1a4a9b72
python3 curate_history.py <new-derivation-directory>
```

The baseline collector independently reconstructed both packet records and all
27 artifacts from Git objects, before adding the new verifier. It checked fix
parents, the parentless introduction and ancestry. `git rev-parse commit:path`
and `git cat-file blob` supplied source/license identities and bytes;
`git diff --no-ext-diff --no-textconv --full-index parent fix -- paths` supplied
forward diffs; `git diff-tree --root --no-commit-id --no-ext-diff --no-textconv
--full-index -p introduction -- path` supplied root additions;
`git show -s --format=%H%n%P%n%B commit` supplied commit records.
Exact commits, source paths, roles, URLs, lengths, SHA-256 values and source Git
blob IDs are recorded in the trust anchor. Both reconstructed packet records
and every artifact were byte-compared to the committed candidates: all matched.

The anchor's `packets` mapping contains those independently generated records,
not values read from the submitted packet ledgers. The optional root README's
SHA-256 was derived from the reviewed baseline documentation. It is allowed only
to support both the committed tree (with README) and collector output (without).
All other root entries and all packet entries must match exactly; symlinks,
including in-directory links, are forbidden. Artifact order is canonical too.
Duplicate JSON keys are rejected. JSON whitespace/key order are not identity.

## Boundaries and regressions

Run `python3 -m unittest -v test_history` for the untrusted-only negative matrix.
It removes every required metadata field, forges every artifact field, removes
each artifact/file, and replaces each artifact's bytes while recomputing all
packet hashes/blob IDs. It also covers empty/deleted inventory, duplicates,
extra files/directories/packets, path escapes, noncanonical/absolute paths,
symlinks, malformed/duplicate-key JSON, attribution and false-as-zero changes.
Representative cases exercise the real CLI: exit 1, actionable stderr, no
success stdout and no traceback. No test changes the trust anchor.

The packets remain development-visible candidates, outside accepted corpus and
scoring. Missing independent source/contract/root-cause adjudication, redaction
audit, observed failure or historical log and pinned external contract remain
admission gaps. The root introduction has no earlier good parent; upstream
lineage is unknown. No historical code is imported, compiled or executed.
