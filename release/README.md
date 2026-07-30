# Release Candidate and Promotion

The release workflows implement the two-phase release architecture resolved in
Issues #18, #12, and #13. A Release Candidate is built once; verification and
Release Promotion only consume and reverify those bytes.

## Candidate workflow

Dispatch `.github/workflows/release-candidate.yml` with:

- the exact `compatibility.json` SDK version;
- `stable`, `prerelease`, or `experimental`;
- a full source commit SHA reachable from `main`.

The workflow rejects an incompatible SemVer/channel pair, version drift,
existing release refs or Releases, and source commits outside `main`. Linux,
macOS/Xcode 16.4, and Windows 2022 lanes produce checksummed fragment
envelopes. Every envelope binds the source SHA, compatibility digest, observed
toolchain, declared payload paths, per-file digest, and Bazel provenance.

One Linux job verifies every envelope through `fragment verify`, imports the
fragments through the checksum-verifying Bazel repository seam, and assembles
the Unity TGZ, Unity ZIP, Godot ZIP, and UPM package tree exactly once.
`candidate.json` binds:

- version and channel;
- exact source SHA;
- exact external/embedded compatibility digest;
- all three final artifact digests.

`candidate verify` also checks both Unity archives against the UPM tree,
checks every distribution content manifest, checks byte-identical embedded
compatibility metadata, and checks `SHA256SUMS`. The candidate bundle is
retained for 30 days and its durable files receive a GitHub artifact
attestation.

## Release Evidence contract

`verification-plan.json` is the complete matrix expanded from
`compatibility.json`. Verification runners consume only the downloaded
candidate bundle and use:

```text
verification/release_evidence.py record --candidate candidate.json ...
```

They must not rebuild or reassemble an artifact. Each evidence file must report
one exact plan row and every required shared suite. The complete evidence
artifact has this shape:

```text
manifest.json
evidence/
  <one JSON file per required environment>
```

`manifest.json` contains only:

```json
{
  "schema_version": 1,
  "evidence": [
    "evidence/example.json"
  ]
}
```

The producing workflow uploads it as
`release-evidence-<version>`. Device, browser, engine, and self-hosted runner
labels are deliberately not invented here: a producer may emit evidence only
for the exact environment it actually ran. Observation-only or `unverified`
evidence cannot pass `gate`.

## Protected promotion

Dispatch `.github/workflows/release-promotion.yml` from `main` with the
candidate version, candidate ID, successful candidate run ID, and successful
complete-evidence run ID. The `release` environment is the human approval
boundary. The workflow has repository-wide serialized concurrency with
cancel-in-progress disabled; only its approved job receives `actions: read`
and `contents: write`.

Promotion performs no build. It verifies the downloaded candidate, all final
bytes, and the complete candidate-bound Release Evidence before calling
`promotion apply`. Reconciliation classifies every destination as absent,
exact, or conflicting before public mutation. Exact state is idempotent;
conflicting refs, assets, release metadata, or bytes fail closed.

The forward-only order is:

1. create the package-only UPM commit object without moving a public ref;
2. create or resume the draft Release and upload missing assets;
3. download and reverify every Release asset;
4. create immutable `v<version>` at the candidate source SHA;
5. create immutable `upm-v<version>` at the verified UPM commit;
6. publish the existing draft Release;
7. fast-forward `upm` for a stable release only;
8. perform final exact reconciliation and write promotion evidence.

The hermetic promotion simulator tests retry after every partial boundary.
The production updater always uses `force: false` for `upm` and exposes no
delete, retarget, overwrite, or asset-clobber operation.

## Withdrawal

Published releases, assets, and immutable tags are never deleted or retargeted.
A severe defect is recorded as a Withdrawn Release, and a strictly newer
corrective version is required. The protected release owner annotates the
existing Release without changing its files, then ships that corrective
version; `upm` can only fast-forward to the newer stable package commit.

The repository must keep GitHub Release immutability enabled and the `release`
environment configured with a required human reviewer. These repository-level
guards complement the workflow and are verified during Issue #32 resolution.
