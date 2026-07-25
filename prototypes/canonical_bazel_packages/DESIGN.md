# Proposed Bazel seams

This document is deliberately concrete, but still a prototype. Names here are
proposals to accept, revise, or reject before production implementation.

## Repository layout

```text
/
├── .bazelversion
├── MODULE.bazel
├── build/
│   ├── BUILD.bazel
│   ├── distribution_fragment.bzl
│   ├── engine_sdk_distribution.bzl
│   ├── platform_transitions.bzl
│   ├── providers.bzl
│   ├── platforms/
│   │   └── BUILD.bazel
│   └── visibility/
│       └── BUILD.bazel
└── packages/
    ├── webview-core/build/api_contract.bzl
    ├── webview-android/build/android_backend.bzl
    ├── webview-ios/build/ios_backend.bzl
    ├── webview-windows/build/windows_backend.bzl
    ├── webview-web/build/web_backend.bzl
    ├── webview-unity/build/unity_adapter.bzl
    └── webview-godot/build/godot_adapter.bzl
```

Each `packages/webview-*` directory has exactly one root `BUILD.bazel`. Its
`src/`, `tests/`, `docs/`, `build/`, and engine-only `distribution/`
directories are ordinary directories in that package, never nested Bazel
packages.

Shared providers, platform transitions, fragment normalization, and final SDK
aggregation live in the root `build/` package. Toolchain- or engine-specific
macros live under the owning Repository Module's `build/` directory and are
loaded through that module's root package label. No module-local `build/`
directory contains a nested `BUILD.bazel`.

## Bazel and Bzlmod baseline

The production root pins:

```text
Bazel                         8.7.0
rules_android                 0.7.3
rules_apple                   4.5.3
rules_cc                      0.2.22
rules_dotnet                  0.21.5
rules_pkg                     1.2.0
rules_rust                    0.71.3
rules_rust_wasm_bindgen       0.71.0
```

The committed `MODULE.bazel.lock` is authoritative. `rules_kotlin` is omitted
because v1 has no Kotlin source. `rules_js` is omitted because Web JavaScript
is a declared payload and no JavaScript toolchain action is needed.
Project-owned string build settings and transitions are implemented directly
in Starlark, without adding `bazel_skylib`.

```starlark
module(name = "verve_webview", version = "0.0.0")

bazel_dep(name = "rules_android", version = "0.7.3")
bazel_dep(name = "rules_apple", version = "4.5.3")
bazel_dep(name = "rules_cc", version = "0.2.22")
bazel_dep(name = "rules_dotnet", version = "0.21.5")
bazel_dep(name = "rules_pkg", version = "1.2.0")
bazel_dep(name = "rules_rust", version = "0.71.3")
bazel_dep(name = "rules_rust_wasm_bindgen", version = "0.71.0")
```

The Android SDK extension remains pinned to API 35 and Build Tools 35.0.0;
Java compilation uses `--release 11` and package manifests declare minSdk 24.
Apple execution uses Xcode 16.4 with iOS 13.0 as the minimum. Windows execution
uses the pinned `windows-2022` image and checksummed WebView2 SDK inputs; its
exact MSVC/Windows SDK versions remain recorded evidence rather than a false
hermetic claim.

## Public build interface

The root BUILD files use only project-owned interface families:
`api_contract`, `webview_core_{native,web}`, platform-specific `*_backend`,
engine-specific `*_adapter`, engine-specific `*_binding`, and
`engine_sdk_distribution`. These are accepted as deep build Modules. They
create or wrap private `rust_library`,
`rust_wasm_bindgen`, `android_library`, `apple_static_xcframework`,
`cc_binary`, code-generation, checksum, staging, and packaging targets.

Only these labels are supported cross-module entry points:

```text
//packages/webview-unity:sdk
//packages/webview-godot:sdk
```

The canonical cross-module internal labels are:

```text
//packages/webview-core:{api_contract,core_native,core_web}
//packages/webview-{android,ios,windows,web}:backend
//packages/webview-{unity,godot}:{adapter,binding_android,binding_ios,binding_windows,binding_web}
```

All compiler, linker, code-generation, staging, manifest, checksum, and
packaging helpers use `//visibility:private`.

## Visibility groups

`build/visibility/BUILD.bazel` contains explicit allowlists:

```starlark
package_group(
    name = "core_consumers",
    packages = [
        "//packages/webview-android",
        "//packages/webview-ios",
        "//packages/webview-windows",
        "//packages/webview-web",
        "//packages/webview-unity",
        "//packages/webview-godot",
    ],
)

package_group(
    name = "backend_consumers",
    packages = [
        "//packages/webview-unity",
        "//packages/webview-godot",
    ],
)

```

`adapter` and every `binding_*` use `//visibility:private`. Their direct tests
are targets in the same root Bazel package, even when their source files live
under `tests/`. Example Apps and cross-package end-to-end verification depend
only on `sdk`; there is no engine-internals allowlist.

`api_contract` is accepted as the third canonical Core target, superseding the
earlier two-target Core graph. Both Engine Adapters consume its generated
engine types and conformance data directly; `core_native` and `core_web`
consume the same semantic source without forcing an Adapter to depend on
either physical transport.

## Distribution fragment provider

There are exactly four cross-rule project providers:

```starlark
ApiContractInfo = provider(
    fields = {
        "rust": "depset of committed, byte-verified Rust snapshots",
        "native": "depset of committed C ABI snapshots",
        "web": "depset of committed JavaScript transport snapshots",
        "unity": "depset of committed Unity C# snapshots",
        "godot": "depset of committed Godot snapshots",
        "docs": "depset of generated reference documentation",
        "conformance": "depset of shared conformance vectors",
    },
)

CorePayloadInfo = provider(
    fields = {
        "transport": "'native' or 'web'",
        "payloads": "immutable logical payload map",
        "abi_metadata": "version and capability metadata File",
        "conformance": "shared conformance-vector Files",
    },
)

PlatformBackendInfo = provider(
    fields = {
        "platform": "canonical platform name",
        "payloads": "immutable logical payload map keyed by profile/architecture",
        "runtime_metadata": "declared runtime and ABI metadata File",
    },
)
```

Compilation rules retain their native Bazel providers. A small packaging rule
adapts their declared outputs to one additional provider:

```starlark
DistributionFragmentInfo = provider(
    fields = {
        "entries": "depset of output files with explicit archive destinations",
        "compatibility": "the byte-identical compatibility.json File",
        "content_manifest": "machine-readable path, size, and SHA-256 manifest",
        "fragment_manifest": "fragment identity, SDK version, platform, architecture, and provenance",
    },
)
```

Canonical `backend` labels expose `PlatformBackendInfo`, not `CcInfo`,
Apple-specific providers, AAR internals, or toolchain objects. Private helper
targets retain those native providers. Each Binding Target selects the logical
payload variants it needs and adapts them into `DistributionFragmentInfo`.

The provider intentionally does not expose toolchain objects, staging
directories, globs, host paths, or mutable dictionaries. Archive destination
collisions, duplicate fragment identities, compatibility-byte mismatches, and
manifest/checksum mismatches are analysis or build failures.

This provider is accepted as the one packaging seam for every `adapter` and
`binding_*`. Platform Backend and compiler rules retain their native providers;
the Binding Target adapts their declared outputs into the fragment. Fragments
never form intermediate archives. Only `sdk` owns the Unity or Godot archive
layout and creation.

Proposed adapter rule:

```starlark
distribution_fragment(
    name,
    srcs,
    destinations,
    compatibility,
    fragment_id,
    platform,
    architecture,
    visibility = ["//visibility:private"],
)
```

`destinations` is a label-keyed string dictionary: every declared source has
one archive-relative destination. The rule writes normalized
`content-manifest.json` and `fragment-manifest.json`; it does not create an
archive.

Archive destinations are normalized UTF-8 forward-slash paths. Absolute paths,
empty segments, `.`/`..`, backslashes, drive prefixes, NUL, duplicate
case-folded paths, and symlinks escaping the declared tree are rejected.
Executable bits are allowlisted rather than copied from the host filesystem.
Timestamps, owners, groups, and archive ordering are fixed by the canonical
packaging rules.

## Configuration and transitions

`//build:release_version` is a project-owned mandatory string build setting and
the only release-version input. Fragment rules read it through a hidden
build-setting attribute and record it in their manifests. `sdk` rejects an
unset/default value, mismatched fragment versions, or non-identical
`compatibility.json` bytes. No module macro accepts a free-form `version`
attribute.

Bazel constraints select physical build capability only:

- Android Backend: `@platforms//os:android`; its private compilation targets
  support `arm64-v8a` and emulator `x86_64`. The release Binding transition
  selects only `arm64-v8a`.
- iOS Backend: `@platforms//os:ios`; `rules_apple` internally forms device
  `arm64` and simulator `arm64/x86_64` slices. The SDK-level iOS attribute is
  not split again.
- Windows: `@platforms//os:windows`, CPU `x86_64`.
- Web: project-owned `//build/platforms:web`, CPU `wasm32`.
- Canonical aggregation: project-owned
  `//build/platforms:canonical_aggregation` on Linux.

The fixed transition targets are:

```text
//build/platforms:release_android_arm64
//build/platforms:release_ios_xcframework
//build/platforms:release_windows_x86_64
//build/platforms:release_web_wasm32
//build/platforms:canonical_aggregation
```

`platform_transitions.bzl` defines one transition per `sdk` attribute and
allows only `//command_line_option:platforms` as an output. It does not change
compilation mode, feature flags, SDK version, or user build options. The iOS
transition selects the iOS XCFramework top-level configuration; the private
`rules_apple` rule owns its device/simulator splits.

Unity/Godot versions, supported patch intervals, browser runtime versions, and
release claims remain in `compatibility.json`; encoding them as Bazel
constraints would turn evidence into build configuration.

This separation is accepted. A selectable Bazel configuration proves that a
toolchain can attempt the build; it never constitutes compatibility evidence
or expand a declared support interval.

`engine_sdk_distribution` uses four separately transitioned attributes:

```starlark
engine_sdk_distribution(
    name = "sdk",
    adapter = ":adapter",
    android = ":binding_android",  # cfg = android_transition
    ios = ":binding_ios",          # cfg = ios_transition; Backend forms slices
    windows = ":binding_windows",  # cfg = windows_transition
    web = ":binding_web",          # cfg = web_transition
    release_version = "//build:release_version",
)
```

A single split transition on one `label_list` is rejected because it would
configure every binding for every platform. Separate attributes keep the
engine × platform composition explicit.

This four-attribute shape is accepted as the canonical interface. The
attribute names are fixed across the Unity and Godot `sdk` declarations, and
each attribute owns only its corresponding platform transition.

Binding release transitions own the shipped architecture set; Backend targets
retain every architecture required for release or verification. In
particular, the Android Backend can be configured for emulator `x86_64` even
though `binding_android` release fragments contain only `arm64-v8a`.
`rules_apple` owns the iOS device/simulator split inside the Backend, so the
SDK-level `ios` attribute applies one iOS transition rather than duplicating
the slice matrix.

When remote execution can satisfy every execution platform, one graph supplies
all four providers. Under pinned-host CI, each host builds and uploads the same
manifested fragment shape; the Linux aggregation invocation consumes those
declared inputs, verifies the provider-equivalent manifests and checksums, and
creates the canonical archive without rebuilding payloads.

This is intentionally a release-only interface: an ordinary development host
builds and verifies individual `binding_*` targets. `sdk` is available only
when the complete remote-execution platform set is present or in the controlled
Linux release-aggregation lane; it does not emulate unavailable platforms or
silently omit their fragments.

### Pinned-host fragment import

Pinned-host lanes upload only declared payload files,
`fragment-manifest.json`, and `content-manifest.json`. After download, the
Linux lane mounts them as a read-only external repository whose BUILD targets
list every file explicitly. A private `fragment_import` rule:

```starlark
fragment_import(
    name = "android",
    files = [
        "payload/verve-webview.aar",
        "fragment-manifest.json",
        "content-manifest.json",
    ],
    fragment_manifest = "fragment-manifest.json",
    content_manifest = "content-manifest.json",
)
```

verifies content hashes, fragment identity, platform/architecture provenance,
and compatibility bytes before returning `DistributionFragmentInfo`.
`engine_sdk_distribution` therefore consumes the same provider shape in
remote-execution and pinned-host modes. The Actions artifact or equivalent
transport container is CI plumbing, not an intermediate or publishable SDK
archive.

## Canonical module trees

These are source ownership templates. Repeated `.meta` companions in the Unity
tree are explicit BUILD inputs even when abbreviated below. None of the
subdirectories contains another `BUILD.bazel`.

```text
packages/webview-core/
├── BUILD.bazel
├── README.md
├── api-contract.yaml
├── build/api_contract.bzl
├── src/native/{lib.rs,abi.rs,lifecycle.rs}
├── src/web/{lib.rs,transport.rs}
├── generated/{rust,native,web,unity,godot,docs,conformance}/
├── tests/
└── tools/update_api_contract.rs

packages/webview-android/
├── BUILD.bazel
├── README.md
├── build/android_backend.bzl
├── src/main/AndroidManifest.xml
├── src/main/java/com/tedliou/verve/webview/
├── src/native/
├── src/runtime-metadata.json
└── tests/

packages/webview-ios/
├── BUILD.bazel
├── README.md
├── build/ios_backend.bzl
├── src/VerveWebViewBackend.{h,m}
├── src/runtime-metadata.json
└── tests/

packages/webview-windows/
├── BUILD.bazel
├── README.md
├── build/windows_backend.bzl
├── src/verve_webview_backend.{h,cc,def}
├── src/runtime-metadata.json
└── tests/

packages/webview-web/
├── BUILD.bazel
├── README.md
├── build/web_backend.bzl
├── src/backend.{js,d.ts}
├── src/runtime-metadata.json
└── tests/

packages/webview-unity/
├── BUILD.bazel
├── README.md
├── build/unity_adapter.bzl
├── src/adapter/
├── src/bindings/{android,ios,windows,web}/
├── distribution/{package.json,README.md,CHANGELOG.md,LICENSE.md}
├── distribution/Runtime/Verve.WebView.asmdef
├── distribution/Editor/
└── tests/

packages/webview-godot/
├── BUILD.bazel
├── README.md
├── build/godot_adapter.bzl
├── src/adapter/
├── src/bindings/android/{AndroidManifest.xml,java}/
├── src/bindings/ios/
├── src/bindings/windows/
├── src/bindings/web/
├── distribution/addons/verve_webview/{plugin.cfg,plugin.gd}
├── distribution/ios/plugins/verve_webview/
└── tests/
```

Generated build outputs never write into these directories. The only
repository-writing helper is the explicit API Contract snapshot updater; its
CI counterpart regenerates into a sandbox and compares rather than updating.

## Canonical target matrix

| Label | Project rule | Direct canonical dependencies | Project provider |
|---|---|---|---|
| `//packages/webview-core:api_contract` | `api_contract` | none | `ApiContractInfo` |
| `//packages/webview-core:core_native` | `webview_core_native` | `:api_contract` | `CorePayloadInfo` |
| `//packages/webview-core:core_web` | `webview_core_web` | `:api_contract` | `CorePayloadInfo` |
| `//packages/webview-android:backend` | `android_backend` | `core_native` | `PlatformBackendInfo` |
| `//packages/webview-ios:backend` | `ios_backend` | `core_native` | `PlatformBackendInfo` |
| `//packages/webview-windows:backend` | `windows_backend` | `core_native` | `PlatformBackendInfo` |
| `//packages/webview-web:backend` | `web_backend` | `core_web` | `PlatformBackendInfo` |
| `//packages/webview-{unity,godot}:adapter` | engine `*_adapter` | `api_contract` | `DistributionFragmentInfo` |
| `//packages/webview-{unity,godot}:binding_<platform>` | engine `*_binding` | `:adapter`, matching `backend` | `DistributionFragmentInfo` |
| `//packages/webview-{unity,godot}:sdk` | `engine_sdk_distribution` | adapter + four bindings | release outputs |

No canonical label depends sideways on another Platform Backend or Engine
Adapter. A binding is the only engine × platform composition root.

## Module declarations

### WebView Core

The semantic source and committed generated snapshots are:

```text
packages/webview-core/
├── api-contract.yaml
└── generated/
    ├── rust/
    ├── native/
    ├── web/
    ├── unity/
    ├── godot/
    ├── docs/
    └── conformance/
```

`api_contract` regenerates all outputs into the Bazel sandbox, compares them
byte-for-byte with these committed snapshots, and returns their typed labels
through `ApiContractInfo`. Engine Adapters package the Unity or Godot snapshots
through this provider; they do not run code generation during distribution
assembly. A private runnable update helper may refresh the committed snapshots,
but it is not a cross-module build interface.

```starlark
api_contract(
    name = "api_contract",
    src = "api-contract.yaml",
    generator = "tools/update_api_contract.rs",
    snapshots = {
        "rust": ["generated/rust/errors.rs"],
        "native": ["generated/native/webview.h"],
        "web": ["generated/web/webview_transport.js"],
        "unity": ["generated/unity/WebViewError.cs"],
        "godot": ["generated/godot/webview_error.gd"],
        "docs": ["generated/docs/errors.md"],
        "conformance": ["generated/conformance/api-contract.json"],
    },
    visibility = ["//build/visibility:core_consumers"],
)

webview_core_native(
    name = "core_native",
    srcs = [
        "src/native/lib.rs",
        "src/native/abi.rs",
        "src/native/lifecycle.rs",
    ],
    api_contract = ":api_contract",
    visibility = ["//build/visibility:core_consumers"],
)

webview_core_web(
    name = "core_web",
    srcs = [
        "src/web/lib.rs",
        "src/web/transport.rs",
    ],
    api_contract = ":api_contract",
    target_compatible_with = ["//build/platforms:web"],
    visibility = ["//build/visibility:core_consumers"],
)
```

The two transport macros wrap private `rust_library`,
`rust_wasm_bindgen`, C-header assembly, and ABI metadata helpers. Their
canonical labels expose only `CorePayloadInfo`; all generator and compilation
helpers are private.

### Platform Backends

Every Platform Backend exposes only `backend`. Representative declarations:

```starlark
android_backend(
    name = "backend",
    core = "//packages/webview-core:core_native",
    manifest = "src/main/AndroidManifest.xml",
    java_srcs = [
        "src/main/java/com/tedliou/verve/webview/VerveWebViewBackend.java",
    ],
    runtime_metadata = "src/runtime-metadata.json",
    java_release = 11,
    min_sdk_version = 24,
    visibility = ["//build/visibility:backend_consumers"],
)

ios_backend(
    name = "backend",
    core = "//packages/webview-core:core_native",
    srcs = ["src/VerveWebViewBackend.m"],
    hdrs = ["src/VerveWebViewBackend.h"],
    runtime_metadata = "src/runtime-metadata.json",
    minimum_os_version = "13.0",
    device_cpus = ["arm64"],
    simulator_cpus = ["arm64", "x86_64"],
    visibility = ["//build/visibility:backend_consumers"],
)

windows_backend(
    name = "backend",
    core = "//packages/webview-core:core_native",
    srcs = ["src/verve_webview_backend.cc"],
    hdrs = ["src/verve_webview_backend.h"],
    win_def_file = "src/verve_webview_backend.def",
    runtime_metadata = "src/runtime-metadata.json",
    architecture = "x86_64",
    webview2_loader = "//third_party/webview2:static_loader",
    visibility = ["//build/visibility:backend_consumers"],
)

web_backend(
    name = "backend",
    core_bundle = "//packages/webview-core:core_web",
    srcs = [
        "src/backend.js",
        "src/backend.d.ts",
    ],
    runtime_metadata = "src/runtime-metadata.json",
    visibility = ["//build/visibility:backend_consumers"],
)
```

These macros encapsulate the proven native rule kinds:
`android_library`, `apple_static_xcframework`, `cc_binary(linkshared=True)`,
and `rust_wasm_bindgen`. Their compilation targets remain private; `backend`
is the deep build Module interface.

The macros set their fixed `target_compatible_with` constraints internally;
callers cannot weaken them. `PlatformBackendInfo.payloads` uses fixed logical
keys:

```text
Android: release/arm64-v8a, verification/x86_64
iOS:     release/xcframework, debug/xcframework,
         release/device-arm64, debug/device-arm64
Windows: release/x86_64/{dll,import_library},
         debug/x86_64/{dll,import_library}
Web:     release/wasm32
```

Bindings fail analysis if they request a key not present for their platform.

Android v1 source is Java 11 in both the shared Backend AAR and the separate
Godot v2 plugin AAR. Kotlin is not required by the resolved interface, so the
production `MODULE.bazel` omits the unused `rules_kotlin` dependency even
though the earlier proof established a compatible version.

### Engine Adapters and Binding Targets

Unity and Godot use identical canonical target names but engine-specific deep
macros. A single generic `webview_binding` was rejected as shallow: Godot
Android must compile an engine plugin AAR, Godot Windows must form a
GDExtension entry point, while Unity mostly packages C#/native payloads.
`unity_binding` and `godot_binding` hide those differences while returning the
same `DistributionFragmentInfo`.

Representative Unity root declaration:

```starlark
unity_adapter(
    name = "adapter",
    srcs = [
        "src/adapter/VerveWebView.cs",
        "src/adapter/VerveWebView.cs.meta",
        "src/adapter/EditorFakeBackend.cs",
        "src/adapter/EditorFakeBackend.cs.meta",
    ],
    api_contract = "//packages/webview-core:api_contract",
    package_inputs = [
        "distribution/package.json",
        "distribution/README.md",
        "distribution/Runtime/Verve.WebView.asmdef",
    ],
    package_destinations = {
        "distribution/package.json": "package.json",
        "distribution/README.md": "README.md",
        "distribution/Runtime/Verve.WebView.asmdef": "Runtime/Verve.WebView.asmdef",
    },
    visibility = ["//visibility:private"],
)

unity_binding(
    name = "binding_android",
    adapter = ":adapter",
    backend = "//packages/webview-android:backend",
    package_inputs = [
        "src/bindings/android/VerveWebViewAndroid.cs",
        "src/bindings/android/VerveWebViewAndroid.cs.meta",
    ],
    package_destinations = {
        "src/bindings/android/VerveWebViewAndroid.cs": "Runtime/Bindings/Android/VerveWebViewAndroid.cs",
        "src/bindings/android/VerveWebViewAndroid.cs.meta": "Runtime/Bindings/Android/VerveWebViewAndroid.cs.meta",
    },
    backend_destinations = {
        "release/arm64-v8a/verve-webview.aar": "Runtime/Plugins/Android/verve-webview.aar",
    },
    platform = "android",
    visibility = ["//visibility:private"],
)

unity_binding(
    name = "binding_ios",
    adapter = ":adapter",
    backend = "//packages/webview-ios:backend",
    package_inputs = [
        "src/bindings/ios/VerveWebViewIos.cs",
        "src/bindings/ios/VerveWebViewIos.cs.meta",
    ],
    package_destinations = {
        "src/bindings/ios/VerveWebViewIos.cs": "Runtime/Bindings/iOS/VerveWebViewIos.cs",
        "src/bindings/ios/VerveWebViewIos.cs.meta": "Runtime/Bindings/iOS/VerveWebViewIos.cs.meta",
    },
    backend_destinations = {
        "release/device-arm64/libverve_webview.a": "Runtime/Plugins/iOS/libverve_webview.a",
    },
    platform = "ios",
    visibility = ["//visibility:private"],
)

unity_binding(
    name = "binding_windows",
    adapter = ":adapter",
    backend = "//packages/webview-windows:backend",
    package_inputs = [
        "src/bindings/windows/VerveWebViewWindows.cs",
        "src/bindings/windows/VerveWebViewWindows.cs.meta",
    ],
    package_destinations = {
        "src/bindings/windows/VerveWebViewWindows.cs": "Runtime/Bindings/Windows/VerveWebViewWindows.cs",
        "src/bindings/windows/VerveWebViewWindows.cs.meta": "Runtime/Bindings/Windows/VerveWebViewWindows.cs.meta",
    },
    backend_destinations = {
        "release/x86_64/verve_webview.dll": "Runtime/Plugins/Windows/x86_64/verve_webview.dll",
    },
    platform = "windows",
    visibility = ["//visibility:private"],
)

unity_binding(
    name = "binding_web",
    adapter = ":adapter",
    backend = "//packages/webview-web:backend",
    package_inputs = [
        "src/bindings/web/VerveWebViewWeb.cs",
        "src/bindings/web/VerveWebViewWeb.cs.meta",
        "src/bindings/web/verve_webview.jslib",
        "src/bindings/web/verve_webview.jslib.meta",
    ],
    package_destinations = {
        "src/bindings/web/VerveWebViewWeb.cs": "Runtime/Bindings/Web/VerveWebViewWeb.cs",
        "src/bindings/web/VerveWebViewWeb.cs.meta": "Runtime/Bindings/Web/VerveWebViewWeb.cs.meta",
        "src/bindings/web/verve_webview.jslib": "Runtime/Plugins/WebGL/verve_webview.jslib",
        "src/bindings/web/verve_webview.jslib.meta": "Runtime/Plugins/WebGL/verve_webview.jslib.meta",
    },
    backend_destinations = {
        "release/wasm32/verve_webview_core.js": "Runtime/Plugins/WebGL/verve_webview_core.js",
        "release/wasm32/verve_webview_core.wasm": "Runtime/Plugins/WebGL/verve_webview_core.wasm",
    },
    platform = "web",
    visibility = ["//visibility:private"],
)

engine_sdk_distribution(
    name = "sdk",
    engine = "unity",
    adapter = ":adapter",
    android = ":binding_android",
    ios = ":binding_ios",
    windows = ":binding_windows",
    web = ":binding_web",
    release_version = "//build:release_version",
    visibility = ["//visibility:public"],
)
```

The Godot root uses the same six target names:

```starlark
godot_adapter(
    name = "adapter",
    srcs = [
        "src/adapter/webview.gd",
        "src/adapter/webview_result.gd",
    ],
    api_contract = "//packages/webview-core:api_contract",
    package_inputs = [
        "distribution/addons/verve_webview/plugin.cfg",
        "distribution/addons/verve_webview/plugin.gd",
        "distribution/addons/verve_webview/README.md",
    ],
    package_destinations = {
        "distribution/addons/verve_webview/plugin.cfg": "addons/verve_webview/plugin.cfg",
        "distribution/addons/verve_webview/plugin.gd": "addons/verve_webview/plugin.gd",
        "distribution/addons/verve_webview/README.md": "addons/verve_webview/README.md",
    },
    visibility = ["//visibility:private"],
)

godot_binding(
    name = "binding_android",
    adapter = ":adapter",
    backend = "//packages/webview-android:backend",
    platform = "android",
    java_srcs = [
        "src/bindings/android/java/VerveWebViewGodotPlugin.java",
    ],
    manifest = "src/bindings/android/AndroidManifest.xml",
    plugin_destination = "addons/verve_webview/bin/verve-webview-godot.aar",
    backend_destinations = {
        "release/arm64-v8a/verve-webview.aar": "addons/verve_webview/bin/verve-webview-backend.aar",
    },
    visibility = ["//visibility:private"],
)

godot_binding(
    name = "binding_ios",
    adapter = ":adapter",
    backend = "//packages/webview-ios:backend",
    platform = "ios",
    entry_srcs = [
        "src/bindings/ios/verve_webview_godot.m",
        "src/bindings/ios/verve_webview_godot.h",
    ],
    package_inputs = [
        "src/bindings/ios/verve_webview.gdip",
    ],
    package_destinations = {
        "src/bindings/ios/verve_webview.gdip": "ios/plugins/verve_webview/verve_webview.gdip",
    },
    plugin_destinations = {
        "release": "ios/plugins/verve_webview/release/VerveWebViewGodot.xcframework",
        "debug": "ios/plugins/verve_webview/debug/VerveWebViewGodot.xcframework",
    },
    visibility = ["//visibility:private"],
)

godot_binding(
    name = "binding_windows",
    adapter = ":adapter",
    backend = "//packages/webview-windows:backend",
    platform = "windows",
    entry_srcs = [
        "src/bindings/windows/verve_webview_godot.cc",
        "src/bindings/windows/verve_webview_godot.h",
    ],
    gdextension_headers = "//third_party/godot:gdextension_headers_4_7_1",
    entry_symbol = "verve_webview_library_init",
    package_inputs = [
        "src/bindings/windows/verve_webview.gdextension",
    ],
    package_destinations = {
        "src/bindings/windows/verve_webview.gdextension": "addons/verve_webview/bin/verve_webview.gdextension",
    },
    plugin_destinations = {
        "release": "addons/verve_webview/bin/verve_webview_godot.windows.release.x86_64.dll",
        "debug": "addons/verve_webview/bin/verve_webview_godot.windows.debug.x86_64.dll",
    },
    backend_destinations = {
        "release/x86_64/dll": "addons/verve_webview/bin/verve_webview_backend.windows.release.x86_64.dll",
        "debug/x86_64/dll": "addons/verve_webview/bin/verve_webview_backend.windows.debug.x86_64.dll",
    },
    visibility = ["//visibility:private"],
)

godot_binding(
    name = "binding_web",
    adapter = ":adapter",
    backend = "//packages/webview-web:backend",
    platform = "web",
    package_inputs = [
        "src/bindings/web/web_export_plugin.gd",
    ],
    package_destinations = {
        "src/bindings/web/web_export_plugin.gd": "addons/verve_webview/export/web_export_plugin.gd",
    },
    backend_destinations = {
        "release/wasm32/verve_webview_core.js": "addons/verve_webview/bin/web/verve_webview_core.js",
        "release/wasm32/verve_webview_core.wasm": "addons/verve_webview/bin/web/verve_webview_core.wasm",
    },
    visibility = ["//visibility:private"],
)

engine_sdk_distribution(
    name = "sdk",
    engine = "godot",
    adapter = ":adapter",
    android = ":binding_android",
    ios = ":binding_ios",
    windows = ":binding_windows",
    web = ":binding_web",
    release_version = "//build:release_version",
    visibility = ["//visibility:public"],
)
```

Engine-specific macros own importer/export metadata and final archive layout.
The engine binding macro owns composition, any engine plugin compilation, and
the explicit mapping from logical Backend payloads to engine installation
paths.

`sdk` accepts no raw package inputs. Engine-common installable files are
explicit inputs to `adapter`; platform-specific installable files are explicit
inputs to the corresponding `binding_*`. The five resulting fragments are the
only file-bearing dependencies of `sdk`.

The public `sdk` target exposes:

- Unity `DefaultInfo`: deterministic UPM `.tgz` and one-outer-directory `.zip`;
- Unity `OutputGroupInfo.package_tree`: the verified tree used to construct
  and compare the generated `upm` branch;
- Godot `DefaultInfo`: the deterministic dual-root Godot `.zip`;
- both engines: `content_manifest`, `compatibility`, and `provenance` output
  groups.

Private helper targets may form these outputs, but callers see only the one
public `sdk` label.

`engine_sdk_distribution` is accepted as a macro with three private layers:

1. `fragment_merge` verifies all providers, rejects destination collisions,
   and forms the read-only package tree;
2. `rules_pkg` `pkg_tar`/`pkg_zip` targets form the deterministic release
   archives proven by the Bazel baseline;
3. `sdk_outputs` exposes the archives and named output groups through the
   single public `sdk` label.

Archive implementation is therefore not duplicated in a monolithic custom
rule.

### Final metadata placement

- Unity inserts one verified `compatibility.json` and
  `content-manifest.json` at the UPM package root.
- Godot inserts the byte-identical compatibility content and its distribution
  content manifest under `addons/verve_webview/`, avoiding files at the
  consumer project root.
- Per-fragment provenance manifests are exposed through
  `OutputGroupInfo.provenance` and retained with release evidence; they are not
  installed in either SDK.
- `fragment_merge` rejects every destination collision. The shared
  compatibility input is provider metadata, not five competing archive
  entries; `sdk` inserts its one canonical copy.

Distribution globs are rejected. Every declarative input and its
archive-relative destination must appear in the BUILD declaration. Adding a
source file without updating this list leaves it out of the fragment, making
package growth fail closed and reviewable.

## Verification declarations

Direct contract/backend/binding tests are private targets in the owning root
BUILD package and test through the canonical target's project provider. They
do not depend on private compiler helpers. The production templates reserve:

```text
//packages/webview-core:contract_check
//packages/webview-core:conformance_native
//packages/webview-core:conformance_web
//packages/webview-<platform>:backend_contract
//packages/webview-<engine>:binding_<platform>_contract
//packages/webview-<engine>:sdk_manifest_check
```

These labels are test/build entry points, not additional Repository Module
interfaces and remain private to CI orchestration. Engine import/export and
runtime checks consume only the final `sdk` outputs in Example Apps.

Static graph verification fails if:

- a Core target depends on a Backend or Engine package;
- a Backend depends on an Engine or another Backend;
- an Adapter depends on a physical Core transport;
- a Binding Target points at a nonmatching Backend;
- an Example App depends on anything other than its engine `sdk`;
- a non-`sdk` canonical target becomes public;
- a module-local nested `BUILD.bazel` appears;
- a distribution input is supplied by a glob or lacks an explicit
  destination.

Archive verification compares the Unity `.tgz`, Unity `.zip`, Unity package
tree, and Godot `.zip` by normalized manifest; checks embedded compatibility
bytes; verifies the outer-directory and dual-root layouts; rejects undeclared
files; and checks that regeneration leaves the committed API Contract
snapshots unchanged.
