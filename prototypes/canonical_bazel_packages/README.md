# PROTOTYPE — canonical Bazel package templates

This throwaway prototype answers one question:

> Can one small build interface describe all seven Repository Modules while
> keeping toolchain helpers private, enforcing the resolved dependency graph,
> and carrying every installable file through one distribution-fragment
> contract?

It does **not** build production SDK payloads. It makes the proposed package
model concrete enough to inspect and challenge before it becomes real
Starlark.

Run it from the repository root:

```bash
python3 prototypes/canonical_bazel_packages/tui.py
```

The terminal explorer shows the complete state after every action. Use `1`–`7`
to select a Repository Module, `j`/`k` to move between targets, and `g` to
switch between target and repository-graph views.

The proposed Starlark seams and representative BUILD declarations are recorded
in [DESIGN.md](DESIGN.md). The executable model in [model.py](model.py) is the
source used by the explorer and its invariant checks.

## Assumptions to react to

1. `adapter`, each `binding_*`, and `sdk` return the same
   `DistributionFragmentInfo`; compilation providers stay private.
2. `sdk` has one split-configured attribute per supported platform instead of
   one label list receiving every split.
3. Engine versions and verified support intervals are compatibility data, not
   Bazel constraint values. Bazel constraints select only platform,
   architecture, and execution capability.
4. Canonical archives are formed on Linux from declared, checksum-verified
   fragment providers. A remote-execution build may produce those providers in
   one graph; the pinned-host CI fallback produces the same provider-shaped
   manifests in separate lanes before aggregation.
5. The seven Repository Modules remain seven root Bazel packages. `build/`,
   `src/`, `tests/`, and `distribution/` never introduce nested packages.

## Validated reactions

- `sdk` is a release-aggregation target. It is buildable only where every
  required remote-execution platform is available or in the controlled Linux
  release-aggregation lane. Ordinary local development builds and verifies
  individual `binding_*` targets; `sdk` does not promise an all-platform local
  build.
- `engine_sdk_distribution` has four named, separately transitioned
  attributes: `android`, `ios`, `windows`, and `web`. A single `label_list`
  under one split transition is rejected because it would configure every
  Binding Target for every platform.
- Bazel constraints describe only physical build capability: operating
  system, architecture, device/simulator environment, Web, and canonical
  aggregation. Engine versions, closed supported patch intervals, verified
  toolchain/runtime versions, and support claims live only in
  `compatibility.json`.
- Every `adapter` and `binding_*` exposes the same
  `DistributionFragmentInfo` packaging interface. A fragment carries explicit
  archive destinations, the shared compatibility file, content checksums, and
  provenance; it is not an archive. Only `sdk` creates the installable UPM or
  Godot archive.
- Distribution inputs are fail-closed. Every source file and archive-relative
  destination is listed explicitly in BUILD declarations; distribution globs
  are forbidden, so an unreviewed new file cannot silently enter a release.
- `adapter` and every `binding_*` are `//visibility:private`. Direct tests are
  declared in the same root Bazel package; Example Apps and cross-package
  end-to-end verification depend only on the public `sdk`.
- WebView Core has three canonical cross-module targets: `api_contract`,
  `core_native`, and `core_web`. Both Engine Adapters and both physical Core
  transports depend on `api_contract`, so generated engine semantics do not
  depend on a native or browser transport.
- Root BUILD declarations use only project-owned `api_contract`,
  `webview_core_{native,web}`, `*_backend`, `*_adapter`, `*_binding`, and
  `engine_sdk_distribution` interfaces. Native compilation, code generation,
  checksum, staging, and packaging rules are private implementation details
  behind them.
- Shared providers, transitions, fragment normalization, and SDK aggregation
  live under the repository-root `build/`. Platform- and engine-specific
  macros live in each Repository Module's `build/*.bzl`; those directories
  contain no `BUILD.bazel` and therefore do not create nested packages.
- In pinned-host CI, downloaded fragment files and manifests are mounted as a
  read-only external repository. A private `fragment_import` rule verifies
  checksums and provenance before recreating `DistributionFragmentInfo`;
  `sdk` never reads an arbitrary CI staging directory. The CI transport
  container is not a publishable SDK archive.
- Platform Backends express every architecture needed for release or
  verification; Binding Target release transitions choose what is shipped.
  Android Backend supports production `arm64-v8a` and emulator `x86_64`, while
  `binding_android` ships only `arm64-v8a`. The iOS Backend lets
  `rules_apple` form the device/simulator slices internally.
- `sdk` accepts no raw package files. Engine-wide installable files belong to
  the `adapter` fragment, platform files belong to their `binding_*` fragment,
  and `sdk` consumes only those five verified fragments plus release-version
  information.
- The required string build setting `//build:release_version` is the only
  version input. Every fragment records it, and `sdk` rejects any fragment
  whose version or `compatibility.json` bytes differ. Individual macros have
  no independent version attribute.
- The one public `sdk` label exposes all release outputs. Unity defaults to
  `.tgz` and one-root `.zip` outputs and offers the verified package tree as an
  output group; Godot defaults to its dual-root `.zip`. Both expose content
  manifests, compatibility, and provenance through common output groups.
- `engine_sdk_distribution` is a macro over a private `fragment_merge` rule,
  proven `rules_pkg` archive targets, and a private `sdk_outputs` rule. The
  merge rule owns semantic verification and the package tree; `rules_pkg` owns
  deterministic archive formation; callers still see only `sdk`.
- Unity embeds one `compatibility.json` and `content-manifest.json` at package
  root; Godot embeds them under `addons/verve_webview/`. Fragment provenance
  manifests remain release evidence rather than SDK content. Every other
  duplicate archive destination is a hard merge failure.
- `packages/webview-core/api-contract.yaml` and committed generated snapshots
  under `generated/{rust,native,web,unity,godot,docs,conformance}/` are the
  canonical semantic source tree. `api_contract` regenerates in a sandbox and
  compares every byte; Engine Adapters consume the matching snapshots through
  that target.
- Android v1 uses Java 11 for the shared Backend and the separate Godot v2
  plugin wrapper. The production Bzlmod graph omits unused `rules_kotlin`;
  earlier proof of its compatibility remains evidence rather than a required
  dependency.
- Canonical `backend` targets expose only a project-owned
  `PlatformBackendInfo` containing logical platform/profile/architecture
  payloads. Native compilation providers remain private; Binding Targets
  select the required payloads and adapt them to `DistributionFragmentInfo`.
