# WebView Core

Owns the engine- and platform-neutral API Contract and lifecycle runtime.

The Rust runtime implements one deterministic state machine for every SDK
Instance. `initialize`, `open`, and `close` are strict single-flight commands;
`dispose` pre-empts active work and is terminal. The runtime also coordinates
the application Surface Lease, validates direct URLs and normalized geometry
before Backend work, and ignores late, duplicate, stale, or cross-instance
completions without emitting a completion event.

## Native C ABI

`include/webview_core.h` is the narrow internal native transport. Callers first
query `verve_webview_get_abi_info`, then create an opaque SDK Instance with one
Backend command sink and one completion event sink. Accepted commands are
non-blocking and complete exactly once through that event sink.

All envelopes use fixed-width fields, explicit byte lengths, and opaque
generation-tagged handles. Input needed after a call is copied by Rust; output
buffers are borrowed only for the callback duration. Neither side frees memory
allocated by the other. A separate optional diagnostic sink receives stale or
duplicate completion diagnostics and is not an Engine Adapter completion seam.

The canonical `core_native` seam validates a real static archive in Bazel's
execution configuration. Final target-architecture linking remains with each
later native Binding Target after that platform's C/C++ linker toolchain is
registered; the Core ticket does not invent platform linker ownership.

The ABI currently accepts direct `http://` and `https://` URLs up to 8192 UTF-8
bytes, initialization option payloads up to 4096 UTF-8 bytes, normalized
geometry values in `0.0..1.0` with positive width and height, and diagnostic
detail up to 1024 UTF-8 bytes.

## Verification

```sh
bazel test //packages/webview-core:all --lockfile_mode=error
bazel build //packages/webview-core:core_native --lockfile_mode=error
```

The native test consumes the generated lifecycle legality vectors and invokes
completion synchronously from the Backend callback, proving callbacks run
without a Core lock held.
