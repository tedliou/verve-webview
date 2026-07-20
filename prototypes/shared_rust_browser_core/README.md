# Shared Rust browser Core export prototype

Tracking ticket: [Prove the shared Rust browser Core in Unity and Godot exports](https://github.com/tedliou/verve-webview/issues/15)

> **PROTOTYPE — throw this branch away after the architecture decision.** None of
> these APIs, build hooks, paths, or fixtures are production code.

## Question

Can a pinned Unity 2021.3 UPM package and Godot 4.7.1 addon automatically place
and load the same byte-identical `wasm32-unknown-unknown` WebView Core Wasm plus
wasm-bindgen `no-modules` JavaScript facade, without consumer copying, a
consumer-owned HTML template, Extension Support, threads, or cross-origin
isolation?

The prototype deliberately uses package-owned post-export hooks. Both hooks copy
the same Bazel-produced bundle beside the engine export and inject two script
tags into the generated `index.html`. The engine transports then exercise
Promise initialization, retained callbacks, explicit invalid/disposed results,
late-completion suppression, and a Rust trap.

## One command

From this directory:

```sh
python3 prototype.py \
  --bazel /path/to/bazel-or-bazelisk \
  --unity "/path/to/Unity-2021.3/Editor/Unity" \
  --godot "/path/to/Godot-4.7.1"
```

The command builds the real Rust/Wasm bundle, stages it into both distributions,
runs release exports, checks injection, and compares SHA-256 values. Missing
engines are reported as `NOT RUN`; that outcome is not evidence of viability.

When invoking a Windows `Unity.exe` from WSL, also pass a **new** directory on a
Windows-mounted drive, for example
`--unity-workspace /mnt/c/Users/me/AppData/Local/Temp/verve-unity-proof`.
The runner copies the throwaway Unity package and project there because Unity
rejects case-sensitive WSL project directories. It refuses to overwrite an
existing directory.

The browser observation can be automated with the dependency-free
`browser/cdp_probe.py` helper after serving an export over HTTP. See
[`EVIDENCE.md`](EVIDENCE.md) for the exact result shape and the current run.

## Required human/browser observation

Serve each export over HTTP (not `file://`) and open it in a browser. The page
prints `VERVE_PROTOTYPE_RESULT` into a `<pre id="verve-prototype-result">` node.
The result must show successful initialization and creation, accepted `open` and
`dispose`, `disposed_instance` for the post-dispose request, zero late-completion
events before the deliberate trap, and `core_trapped` for the trap.

Before resolving the ticket, also repeat initialization with the Core Wasm
missing and then corrupted, and confirm each Engine Adapter receives an explicit
initialization failure rather than hanging. Unity must be a non-development
WebGL build with High managed stripping so the result also proves the rooted
`MonoPInvokeCallback` survived IL2CPP stripping.

## What does not count

- The shape-only Wasm under `prototypes/bazel_rules_baseline/fixtures/web`.
- A Unity 6 export in place of Unity 2021.3.
- A Godot export without the official 4.7.1 Web template.
- Hash equality before the engine export hooks run.
- Loading through a consumer-owned Web template or manual file copy.
