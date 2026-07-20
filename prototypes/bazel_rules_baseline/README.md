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
| rules_android | 0.7.3 | Bzlmod resolution; declared AAR output built with API 35 / Build Tools 35.0.0 and Java `--release 11` |
| rules_apple | 4.5.3 | Bzlmod resolution; real static XCFramework built with Xcode 16.4 (16F6), device `arm64` and simulator `arm64/x86_64` |
| rules_cc | 0.2.22 | Bzlmod resolution; host packaging helper |
| rules_dotnet | 0.21.5 | Bzlmod resolution |
| rules_kotlin | 2.4.0 | Bzlmod resolution with rules_android 0.7.3 |
| rules_pkg | 1.2.0 | Deterministic archive production |
| rules_rust | 0.71.3 | Bzlmod resolution |
| rules_rust_wasm_bindgen | 0.71.0 | Resolves to rules_rust 0.71.3 |

選擇 Bazel 8 而非 Bazel 9，是因為這是所有直接 ruleset 官方測試線的共同交集；`MODULE.bazel.lock` 固定完整 transitive graph。

原生 proof 另外固定 Android API 35 / Build Tools 35.0.0、AAR minSdk 24、Xcode 16.4、iOS deployment target 13，以及 GitHub `windows-2022` runner。Android SDK 必須同時安裝 `platform-tools`（`rules_android` toolchain 會解析 `adb`）。`windows-2022` 與 GitHub runner image 本身仍是可變標籤；MSVC 與 Windows SDK 的精確 subversion 尚未固定，因此只能鎖 Bazel/rules 與產物約束，不能把 host toolchain 稱為完整 hermetic lock。

## Run

```sh
bazel mod graph
bazel build :representative_fragments
python verify_shapes.py
```

本機以 Bazel 8.7.0 重建兩次，四個 archive 的 SHA-256 相同。跨 OS proof 另以 `.gitattributes` 固定文字換行與 binary checkout，避免 Windows CRLF 轉換污染輸入。`rules_pkg` 的 zip helper 需要 C++ toolchain；因此 packaging lane 必須提供明示且固定的 compiler image，不能把未追蹤的 host autodetection 稱為 hermetic。

Ubuntu、macOS 與 Windows 產出的 archive 內容清單與 uncompressed bytes 相同；Unity tar 也達成三個 OS byte-identical。ZIP 的 Windows bytes 仍不同，差異限定在 central-directory 的 `version made by` host field（Windows 為 FAT/0，Unix 為 Unix/3）。所以 release policy 必須讓 Android AAR、XCFramework zip 與 Godot zip 只在單一受控 Linux aggregation lane 形成 canonical bytes；其他 OS 只產出帶 checksum manifest 的 payload fragments，不能各自重建最終 ZIP 後視為同一 release artifact。

CI 證據：[run 29744049856](https://github.com/tedliou/verve-webview/actions/runs/29744049856) 在 commit `de2b685` 通過 `ubuntu-24.04`、`macos-15` 與 `windows-2022`。其中 Android AAR 冷建置執行 1,237 actions、耗時 794 秒，顯示 production CI 必須為這條 lane 配置明確的 Bazel cache policy。

## Artifact-equivalence constraints

- Android AAR：真實 Bazel AAR 根目錄含 `AndroidManifest.xml` 與 `classes.jar`，manifest 固定 `minSdkVersion=24`。Godot 官方 v2 Gradle shape 還要求 manifest 的 `org.godotengine.plugin.v2.<PluginName>` init-class metadata、對 Godot Android library 的非內嵌 dependency，以及 addon 內的 `EditorExportPlugin`；目前只達成 AAR container equivalence，不是 Godot plugin equivalence。
- Apple：真實 static XCFramework 固定 device `arm64` 與 simulator universal `arm64/x86_64`、最低 iOS 13；驗證器會解析 fat archive 並確認每個 slice 都是 `ar`。官方 Godot shape 另要求 `res://ios/plugins` 下的 `.gdip`、相對 binary path 與 Godot headers/init ABI；目前只達成 library/container equivalence。
- Windows：真實 PE32+ x86_64 DLL 已由 `windows-2022` lane 產生；Godot distribution 以 `.gdextension` feature tag `windows.x86_64` 選 DLL。官方 SCons/godot-cpp shape另要求 `.gdextension` 的 `entry_symbol` 確實由 DLL 匯出、Godot ABI headers、相符 CRT/calling convention，以及 debug/release feature matrix；目前只達成 PE/container equivalence。
- Unity：單一 UPM tree 固定 package id、Unity 2021.3 baseline 與四個 platform payload paths；stable `.meta` importer metadata 會在 Repository Module layout ticket 定義後加入 proof。
- Godot：同一 archive 同時保留 `addons/verve_webview/` 與 project-root `ios/plugins/verve_webview/`；不能把 iOS plugin 錯放到 addon root。
- Web：兩個 Engine SDK Distributions 必須攜帶 byte-identical independent Rust browser Core bundle；export placement 由另一張 prototype ticket 驗證。

Godot 版本本身目前也不能形成 stable native lock：Godot 最新 stable 已是 4.7.1，但 `godot-cpp` 官方最後一個與 Godot 版本對應的 stable tag 是 `godot-4.5-stable`；新版本線只有 `10.0.0-rc1`，且其官方相容性說明尚未提供一個可直接鎖定的 Godot 4.7 stable release。架構規格應保留 Godot 4.7.1 為 Editor/export-template baseline，但在 stable `godot-cpp` reference 或經核准的精確 commit 通過 SCons ABI comparison 前，不得宣稱 Windows GDExtension artifact-equivalent。

## Not proven yet

這個 proof 能安全回答的是「Bazel 8.7.0 與上述 rules graph 可鎖，且三種 host-native container 可由宣告式 target 產生」。它不能證明 Engine import/runtime compatibility。下列 gate 通過前，不應把候選版本稱為 production-safe engine lock：

- Android Godot v2 metadata、Godot dependency scope、EditorExportPlugin 與官方 Gradle reference import/export。
- `.gdip` discovery、Godot initialization ABI，以及 Unity/Godot 對真實 iOS 13 XCFramework 的 consumption。
- 固定 MSVC/Windows SDK/WebView2 SDK subversions，並以可支援 Godot 4.7.1 的精確 `godot-cpp` SCons reference 比較 exports、CRT 與 ABI。
- Pinned Unity 2021.3 與 Godot stable Editor 匯入、export 與 runtime smoke tests。

這些 host/engine-owned gates 應保留獨立 cache namespace；不得因 Bzlmod graph 或 shape archive 成功而降級或省略。
