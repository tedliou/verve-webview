# Prototype evidence

Tracking ticket: [#15](https://github.com/tedliou/verve-webview/issues/15)

This is evidence for an architecture decision, not production test coverage.
Both pinned engine gates passed.

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

## Unity 2021.3.45f2: required gate passed

Environment: Unity Personal `2021.3.45f2 (88f88f591b2e)` installed with WebGL
Build Support; release WebGL; High managed stripping; IL2CPP/Emscripten; package
imported through UPM. The build was launched through Unity CLI:

```text
unity.exe --non-interactive run <project> --editor-version 2021.3.45f2 -- -nographics -executeMethod BuildPrototype.Build -logFile -
```

The real browser export returned:

```json
{"engine":"unity","init":"{\"ok\":true,\"code\":\"ready\",\"detail\":null}","create":"{\"ok\":true,\"code\":\"created\",\"handle\":1}","open":"{\"ok\":true,\"code\":\"accepted\",\"handle\":1,\"generation\":1}","dispose":"{\"ok\":true,\"code\":\"disposed\",\"handle\":1,\"generation\":2}","disposedRequest":"{\"ok\":false,\"code\":\"disposed_instance\",\"handle\":1,\"generation\":3}","lateCompletionEvents":0,"trap":"{\"ok\":false,\"code\":\"core_trapped\",\"detail\":\"RuntimeError: unreachable\"}"}
```

Removing the exported Wasm produced `core_load_failed` with an HTTP status
failure. Replacing it with JavaScript bytes produced `core_load_failed` with a
WebAssembly magic-word `CompileError`. Neither case hung. The successful AOT
callbacks after High managed stripping also prove that the rooted
`MonoPInvokeCallback` delegates survived release stripping.

## Unity 6: compatibility precheck passed

Environment: Unity `6000.3.20f1`, release WebGL, High managed stripping,
IL2CPP/Emscripten, package imported through UPM. This precheck preceded the
required Unity 2021.3.45f2 gate above.

The real browser export returned:

```json
{"engine":"unity","init":"{\"ok\":true,\"code\":\"ready\",\"detail\":null}","create":"{\"ok\":true,\"code\":\"created\",\"handle\":1}","open":"{\"ok\":true,\"code\":\"accepted\",\"handle\":1,\"generation\":1}","dispose":"{\"ok\":true,\"code\":\"disposed\",\"handle\":1,\"generation\":2}","disposedRequest":"{\"ok\":false,\"code\":\"disposed_instance\",\"handle\":1,\"generation\":3}","lateCompletionEvents":0,"trap":"{\"ok\":false,\"code\":\"core_trapped\",\"detail\":\"RuntimeError: unreachable\"}"}
```

Removing the exported Wasm produced `core_load_failed` with an HTTP status
failure. Replacing it with JavaScript bytes produced `core_load_failed` with a
WebAssembly magic-word `CompileError`. Neither case hung.

## Decision

The byte-identical independent `wasm32-unknown-unknown` browser Core bundle is
viable as the v1 distribution contract. Unity can deliver it from UPM through a
package-owned post-build hook, while Godot can deliver it through an addon-owned
export plugin. Consumers need no manual copy, custom HTML template, Extension
Support, threads, or cross-origin isolation. The Unity-owned
`wasm32-unknown-emscripten` fallback is not required for v1.
