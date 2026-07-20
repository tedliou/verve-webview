# Bazel rules baseline proof

追蹤票：[Prove the Bazel rules baseline and engine artifact equivalence](https://github.com/tedliou/verve-webview/issues/13)

這是 architecture proof，不是 production feature。它回答兩個較窄、可在一般 CI runner 重跑的問題：

1. WebView SDK v1 需要的 Bzlmod rules 能否由同一個 Bazel release line 解析？
2. 宣告式 packaging graph 能否產生固定、可檢查且可重現的 Engine SDK Distribution 片段？

fixture 內的 `.aar`、`.a`、`.dll` 與 `.wasm` 是刻意標示的 shape-only inputs；它們不證明 platform compiler、ABI、Engine import 或 runtime compatibility。

## Candidate baseline

| Component | Version | Evidence covered here |
| --- | --- | --- |
| Bazel | 8.7.0 | Local resolution and packaging; CI host matrix |
| rules_android | 0.7.3 | Bzlmod resolution; AAR shape only |
| rules_apple | 4.5.3 | Bzlmod resolution; XCFramework shape only |
| rules_cc | 0.2.22 | Bzlmod resolution; host packaging helper |
| rules_dotnet | 0.21.5 | Bzlmod resolution |
| rules_kotlin | 2.4.0 | Bzlmod resolution with rules_android 0.7.3 |
| rules_pkg | 1.2.0 | Deterministic archive production |
| rules_rust | 0.71.3 | Bzlmod resolution |
| rules_rust_wasm_bindgen | 0.71.0 | Resolves to rules_rust 0.71.3 |

選擇 Bazel 8 而非 Bazel 9，是因為這是所有直接 ruleset 官方測試線的共同交集；`MODULE.bazel.lock` 固定完整 transitive graph。

## Run

```sh
bazel mod graph
bazel build :representative_fragments
python verify_shapes.py
```

本機以 Bazel 8.7.0 重建兩次，四個 archive 的 SHA-256 相同。`rules_pkg` 的 zip helper 需要 C++ toolchain；因此 packaging lane 必須提供明示且固定的 compiler image，不能把未追蹤的 host autodetection 稱為 hermetic。

## Artifact-equivalence constraints

- Android AAR：根目錄必須含 `AndroidManifest.xml` 與 `classes.jar`，manifest 固定 `minSdkVersion=24`。Godot v2 plugin 的真實 AAR仍需與官方 Gradle template 比較 manifest metadata、Godot dependency scope、resources 與 native ABI entries。
- Apple：XCFramework shape 固定 device `arm64` 與 simulator `arm64/x86_64`，最低 iOS 13。真實 archive、symbols、headers 與 `.gdip` discovery 必須在 pinned macOS/Xcode lane 驗證。
- Windows：Godot distribution 以 `.gdextension` feature tags 選 `windows.x86_64` DLL；真實 DLL 必須由 pinned MSVC/Windows SDK/WebView2 SDK lane 與同版 `godot-cpp` SCons reference 比較 exports、CRT、calling convention 與 ABI。
- Unity：單一 UPM tree 固定 package id、Unity 2021.3 baseline 與四個 platform payload paths；stable `.meta` importer metadata 會在 Repository Module layout ticket 定義後加入 proof。
- Godot：同一 archive 同時保留 `addons/verve_webview/` 與 project-root `ios/plugins/verve_webview/`；不能把 iOS plugin 錯放到 addon root。
- Web：兩個 Engine SDK Distributions 必須攜帶 byte-identical independent Rust browser Core bundle；export placement 由另一張 prototype ticket 驗證。

## Not proven yet

這個 branch 成功不等於整張追蹤票完成。下列 gate 通過前，不應把候選版本稱為 production-safe lock：

- Android SDK/Build Tools/JDK lane 產出真實 API 24 AAR，並與 Godot Gradle reference shape 比較。
- macOS/Xcode lane 產出真實 iOS 13 static archive/XCFramework，並驗證 Unity 與 Godot consumption。
- Windows/MSVC lane 產出 WebView2 DLL/GDExtension，並與同版 Godot SCons output 做 ABI equivalence。
- Pinned Unity 2021.3 與 Godot stable Editor 匯入、export 與 runtime smoke tests。

這些 host/engine-owned gates 應保留獨立 cache namespace；不得因 Bzlmod graph 或 shape archive 成功而降級或省略。
