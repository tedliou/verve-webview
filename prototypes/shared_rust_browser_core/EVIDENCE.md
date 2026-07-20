# Prototype evidence

Tracking ticket: [#15](https://github.com/tedliou/verve-webview/issues/15)

This is evidence for an architecture decision, not production test coverage.
The ticket remains open because the required Unity 2021.3 run has not happened.

## Bundle identity

The package-owned Unity and Godot export hooks produced these byte-identical
files after export:

```text
65313fa586f552ed56da6178915afa2da31f49b52d5f7b12b4960458c9c4b977  verve_webview_core.js
785af114cc7e843d81faf66ddd6aac4370a10dabc088384283854d69b422fd88  verve_webview_core_bg.wasm
0e9efc1669110a756db4f7120a817ba13b2041e4a3b65ef395bce99c341c4ce1  verve_webview_core_facade.js
```

The third digest identifies the current hand-written facade. A fresh run must
print and compare its own digests rather than treating these values as fixtures.

## Godot 4.7.1: required gate passed

Environment: official Godot `4.7.1.stable.official.a13da4feb` editor and Web
export template; release Web export; Extension Support off; threads off; empty
custom HTML shell.

The real browser export returned:

```json
{"engine":"godot","phase":"ready","init":"{\"ok\":true,\"code\":\"ready\",\"detail\":null}","create":"{\"ok\":true,\"code\":\"created\",\"handle\":1}","open":"{\"ok\":true,\"code\":\"accepted\",\"handle\":1,\"generation\":1}","dispose":"{\"ok\":true,\"code\":\"disposed\",\"handle\":1,\"generation\":2}","disposedRequest":"{\"ok\":false,\"code\":\"disposed_instance\",\"handle\":1,\"generation\":3}","lateCompletionEvents":0,"trap":"{\"ok\":false,\"code\":\"core_trapped\",\"detail\":\"RuntimeError: unreachable\"}"}
```

Removing the exported Wasm produced `core_load_failed` with an HTTP status
failure. Replacing it with JavaScript bytes produced `core_load_failed` with a
WebAssembly magic-word `CompileError`. Neither case hung.

## Unity 6: compatibility precheck passed, not the required gate

Environment: Unity `6000.3.20f1`, release WebGL, High managed stripping,
IL2CPP/Emscripten, package imported through UPM. This only reduces risk; ticket
#15 explicitly requires Unity 2021.3.

The real browser export returned:

```json
{"engine":"unity","init":"{\"ok\":true,\"code\":\"ready\",\"detail\":null}","create":"{\"ok\":true,\"code\":\"created\",\"handle\":1}","open":"{\"ok\":true,\"code\":\"accepted\",\"handle\":1,\"generation\":1}","dispose":"{\"ok\":true,\"code\":\"disposed\",\"handle\":1,\"generation\":2}","disposedRequest":"{\"ok\":false,\"code\":\"disposed_instance\",\"handle\":1,\"generation\":3}","lateCompletionEvents":0,"trap":"{\"ok\":false,\"code\":\"core_trapped\",\"detail\":\"RuntimeError: unreachable\"}"}
```

Removing the exported Wasm produced `core_load_failed` with an HTTP status
failure. Replacing it with JavaScript bytes produced `core_load_failed` with a
WebAssembly magic-word `CompileError`. Neither case hung.

## Remaining decision gate

Repeat the Unity run with `2021.3.48f1` plus its WebGL Build Support module. If
the UPM import, `.jslib` preprocessing, High-stripping IL2CPP export, browser
result, error injections, and post-export hashes all pass, the independent
browser Core route is viable. Any incompatibility specific to Unity 2021.3 is
the trigger to evaluate the ticket's Unity-owned Emscripten fallback.
