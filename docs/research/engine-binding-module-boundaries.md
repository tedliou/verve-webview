# Engine Adapter 與 Binding/Composition 的實體模組邊界

> 調查日期：2026-07-19
> 範圍：Bazel monorepo；Unity 2021+、目前穩定版 Godot；Android、iOS、Windows 11 / WebView2、Unity Web / Godot Web iframe。
> 資料原則：僅採用 Bazel、Unity、Godot、Android、Apple、Microsoft 的官方文件。本文中的「建議」與「判準」是根據這些一手資料做出的架構推論，不是各廠商直接給出的模組設計規範。

## 結論摘要

Engine Adapter 與引擎 × 平台 Binding/Composition **應保持兩個邏輯責任邊界，但不必預設為兩個實體模組**。是否拆分要分三層判斷：

1. **Bazel package（`BUILD` 所在目錄）**：本專案通常不必拆。`packages/webview-unity` 與 `packages/webview-godot` 各自維持一個 Bazel package，即可容納 adapter 與其平台 bindings。Bazel 定義 package 為含有 `BUILD` / `BUILD.bazel` 的目錄，package 本身是相關檔案與 targets 的容器；因此責任不同不等於必須增加 `BUILD` 邊界。[Bazel：Workspaces, packages, and targets](https://bazel.build/concepts/build-ref)
2. **Bazel target**：只在編譯工具鏈、規則種類、相依、輸出格式或可見性需要獨立時拆。相同 package 可以宣告多個 targets；`select()` 可依平台切換 `srcs`、`deps` 等屬性，適合在單一 target 不會污染相依圖時保留整合。[Bazel：Configurable Build Attributes](https://bazel.build/docs/configurable-attributes)
3. **發佈 artefact**：建議每個引擎一個，而不是每個引擎 × 平台一個。Unity 的 custom package 可以同時含 C#、assemblies 與 native plugins；Godot addon/Android plugin 的官方安裝形態也允許一個 `addons/<plugin>` 目錄帶入腳本、設定與平台 binaries。[Unity：Creating custom packages](https://docs.unity3d.com/Manual/CustomPackages.html)；[Godot：Installing plugins](https://docs.godotengine.org/en/stable/tutorials/plugins/editor/installing_plugins.html)；[Godot：Android plugin packaging](https://docs.godotengine.org/en/stable/tutorials/platform/android/android_plugin.html)

因此，適合本專案的預設是：

- `packages/webview-unity`：一個 Bazel package、一個 Unity UPM 發佈物；內部依需要有 `adapter`、`android_binding`、`ios_binding`、`windows_binding`、`web_binding` 多個 targets。
- `packages/webview-godot`：一個 Bazel package、一個 Godot addon 發佈物；內部依需要有 `adapter` 與平台 bindings 多個 targets。
- **不要**為了表達邏輯責任而先建立 `webview-<engine>-<platform>` 實體 package；有下文的拆分訊號時才建立 target。只有出現獨立擁有權、公開可見性或獨立發佈週期時，才再升級成獨立 Bazel package／發佈物。

另外，現有需求中的 **Android 5.0 無法同時滿足「Unity 2021+」與「最新穩定 Godot」**：Unity 2021.3 官方最低為 Android 5.1 / API 22，而目前 stable Godot 文件的原生匯出最低為 Android 7.0（Compatibility renderer；Forward+/Mobile 更高）。這是支援矩陣決策，不是模組拆分可以解決的問題。[Unity 2021.3 Android requirements](https://docs.unity3d.com/2021.3/Documentation/Manual/android-requirements-and-compatibility.html)；[Godot stable system requirements](https://docs.godotengine.org/en/stable/about/system_requirements.html)

## 1. 先區分邏輯邊界與實體邊界

### 邏輯責任邊界（永遠保留）

- **Engine Adapter**：把公開 SDK 與 WebView Core 的生命週期、狀態、錯誤語意轉換成 Unity 或 Godot 使用者看到的 API；負責引擎主執行緒、物件／Node 生命週期與回呼形式。
- **Binding/Composition**：把某引擎的呼叫接到某平台 backend；只處理 JNI、P/Invoke、Godot singleton、GDExtension entry point、`.jslib`、`JavaScriptBridge`、平台 binary 選擇與封裝，不擁有 WebView 行為規則。

即使兩者位於同一個 target 或發佈物，也應以 namespace、內部目錄、internal visibility、介面與測試分開。這避免平台條件判斷進入公開 API／狀態機，同時不為了概念純度製造沒有建置價值的 targets。

### 實體邊界（按需要建立）

| 邊界 | 它實際解決什麼 | 本專案何時才值得拆 |
|---|---|---|
| Bazel package | 檔案歸屬、跨 package label、package 級預設 visibility | 需要 package 級擁有權／visibility；子樹有獨立維護者；或 BUILD 已大到難以導航 |
| Bazel target | 編譯／連結 action、toolchain、deps、輸出、cache 與測試單位 | 規則種類、工具鏈、輸出格式、平台相依或測試環境不同 |
| 發佈 artefact | 使用者安裝、版本、相容性與更新單位 | 使用者可獨立選裝；需獨立版本；授權／大小要求禁止一起配送；或引擎的套件格式無法容納該平台檔案 |

Bazel 的 target visibility 是控制「哪些 targets 可以依賴此 target」的機制；同 package targets 天然可互相使用。因此若 adapter 與 binding 需要不同外部可見性，拆 target 已足夠，不必直接拆 package。[Bazel：Visibility](https://bazel.build/concepts/visibility)

## 2. 不拆實體模組的充分條件

以下條件應分別套用到 package、target、發佈物；不是全部同時成立才允許任何合併。

### 2.1 可以共用一個 Bazel package

滿足下列條件時，adapter 與所有該引擎 bindings 放在同一 `packages/webview-<engine>/BUILD.bazel`：

- 同一團隊／模組擁有者維護，變更通常一起 review。
- 都只服務同一引擎，沒有另一個 repo 需要直接依賴其中某個 binding 的 source label。
- 外部使用者只需依賴公開 facade；binding targets 可標成 private。
- `src/adapter/` 與 `src/bindings/<platform>/` 的檔案結構已足以表達責任邊界。
- 不需要針對某子樹設定不同 package 預設 visibility。

這符合 Bazel package 作為「相關 source files + targets 的容器」的定義；加入巢狀 `BUILD` 反而會立即建立不能跨越的 package boundary。[Bazel：Workspaces, packages, and targets](https://bazel.build/concepts/build-ref)

### 2.2 可以共用一個 Bazel target

只有在以下條件都成立時，adapter 與某 binding 才合成同一 target：

- 使用同一 Bazel rule kind 與 toolchain（例如都是 C# source；或都是同一個 C++ library）。
- 產生同一個主要輸出，不需要額外 AAR、`.a` / `.xcframework`、DLL、Wasm 或 `.jslib` 建置 action。
- 平台專屬 deps 可用 `select()` 完整隔離，未選平台不會分析／編譯／連結不相容依賴；Bazel 官方明確支援用 `select()` 切換 `srcs`、`deps`、resources 等 configurable attributes。[Bazel：Configurable Build Attributes](https://bazel.build/docs/configurable-attributes)
- adapter 與 binding 的 consumer visibility 相同。
- 兩者用相同測試 runner 即可驗證，沒有必須在 Android instrumentation、Xcode、Windows native host 或 browser 中單獨執行的測試。
- 兩者版本與變更節奏相同；binding 不是可替換實作。

實務上，這通常只適用於「以引擎語言寫成、僅含薄呼叫宣告／路由」的 binding，例如 Unity C# 中受平台條件保護的 P/Invoke/JNI wrapper，或 Godot GDScript 中受 feature check 保護的 `JavaScriptBridge` 路由。

### 2.3 可以共用一個發佈 artefact

滿足以下條件時，以一個 Unity package 或一個 Godot addon 配送所有平台：

- 消費者期待「安裝一次即可在支援平台切換」，而不是逐平台挑選 SDK。
- 平台 binaries 可由引擎的 importer／exporter 自動篩選，不會進入錯誤平台的最終 build。
- 所有平台遵循同一公開 SDK 版本；不需單獨發布 security fix 或 hotfix。
- 套件大小與授權允許一起配送。
- 缺少某平台工具鏈時，套件仍可被其他平台匯入，不會在 Editor import 階段硬失敗。

Unity 官方 custom package 可包含 C# scripts、assemblies、native plugins 與其他 assets，且建議 layout 本來就以一個 `package.json` 配一個 `Runtime/` 樹；Plugin Inspector 再控制各 plugin file 被哪些平台 build 使用。[Unity：Creating custom packages](https://docs.unity3d.com/Manual/CustomPackages.html)；[Unity 2021.3：Package layout](https://docs.unity3d.com/2021.3/Documentation/Manual/cus-layout.html)；[Unity：Plugin Inspector](https://docs.unity3d.com/Manual/plug-in-inspector.html)

Godot addon 以 `addons/<plugin_name>` 目錄安裝；Android v2 plugin 的官方 packaging 範例也把 export script、`plugin.cfg`、`.gdextension` 與產出 binaries 放在同一 addon 目錄。因此「一個 addon 發佈物含多個平台 payload」是可行的；實際 binary 載入仍由平台設定選擇。[Godot：Installing plugins](https://docs.godotengine.org/en/stable/tutorials/plugins/editor/installing_plugins.html)；[Godot：Android plugins](https://docs.godotengine.org/en/stable/tutorials/platform/android/android_plugin.html)；[Godot：`.gdextension` libraries](https://docs.godotengine.org/en/stable/tutorials/scripting/gdextension/gdextension_file.html)

## 3. 必須拆 Bazel target 的訊號

只要出現任一項，adapter 與 binding 至少拆成不同 target；仍可留在同一 Bazel package 與發佈物：

1. **不同 rule kind／toolchain**：C# adapter 對上 Android AAR、Objective-C++ static library、Win32 C++ DLL、Emscripten/Wasm 或 `.jslib` packaging。
2. **不同輸出格式或架構矩陣**：需要 arm64-v8a AAR/native `.so`、iOS device/simulator `.xcframework`、Windows x64/arm64 DLL 等獨立產物。
3. **引擎專屬編譯相依**：Godot Android plugin 是依賴 Godot Android library、繼承 `GodotPlugin`、帶特定 manifest metadata 的 Android library；它不能與普通 Android backend 或 Unity Android wrapper 當成同一 target。[Godot：Android plugin v2 architecture](https://docs.godotengine.org/en/stable/tutorials/platform/android/android_plugin.html)
4. **靜態 vs 動態連結不同**：Unity iOS 以 `DllImport("__Internal")` 呼叫，Unity 會把 `.a/.m/.mm/.c/.cpp/.h` 複製到 Xcode project；Windows native plugin 則是動態 library。兩者無法由一個相同 link action 產出。[Unity 2021.3：Building plug-ins for iOS](https://docs.unity3d.com/2021.3/Documentation/Manual/PluginsForIOS.html)
5. **瀏覽器整合機制不同**：Unity Web 使用 `.jslib` JavaScript plugin 並由 C# extern 呼叫；Godot 的 `JavaScriptBridge` 只存在於 Web export。共用 iframe DOM 邏輯可以是同一份 JS core，但兩個引擎入口需要各自的 binding target。[Unity：Interaction with browser scripting](https://docs.unity3d.com/Manual/webgl-interactingwithbrowserscripting.html)；[Godot：JavaScriptBridge](https://docs.godotengine.org/en/stable/classes/class_javascriptbridge.html)
6. **runtime/架構選擇**：WebView2 loader DLL 是 native 且 architecture-specific；若動態配送 loader，必須按 x86/x64/arm64 產出／選擇，適合獨立 Windows target。[Microsoft：Distribute your app and the WebView2 Runtime](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
7. **不同測試環境**：binding 的正確性只能在裝置、Xcode exported project、Windows native window 或 browser DOM 驗證，而 adapter 可用純引擎測試。
8. **不同 visibility**：公開 adapter target 不應把低階 JNI/PInvoke/GDExtension symbols 變成公共依賴。Bazel visibility 就是為了執行這種 API／implementation 區分。[Bazel：Visibility](https://bazel.build/concepts/visibility)

## 4. 各引擎／平台的具體判斷

### Unity（2021+）

#### Unity adapter 本身

建議保持一個 C# facade/adapter target，公開最窄 API。Unity assembly definition 支援 `includePlatforms` / `excludePlatforms`，而 native plugin importer 也支援指定平台與 CPU；因此平台條件可以留在同一 UPM 發佈物，不代表必須每平台分 package。[Unity：Assembly Definition File Format](https://docs.unity3d.com/Manual/AssemblyDefinitionFileFormat.html)；[Unity：Plugin Inspector](https://docs.unity3d.com/Manual/plug-in-inspector.html)

#### Unity × Android

- **可不拆 target 的情況**：binding 只是一小段 C#，透過 Unity 的 `AndroidJavaObject` / `AndroidJavaClass` 呼叫已存在的 Android backend AAR，且用平台條件保護；Unity 官方 API 本身就是 C# 到 JNI 的高階介面。[Unity：Call Java and Kotlin plug-in code from C#](https://docs.unity3d.com/Manual/android-plugins-java-code-from-c-sharp.html)
- **必拆 target 的情況**：需要產出 AAR、Java/Kotlin source plugin、Android manifest/resource、native `.so`，或該 AAR 依賴 Unity classes。此時 C# adapter 與 Android build action 不同。
- **不能和 Godot Android binding 合成同一 AAR**：Godot v2 AAR 必須依賴 Godot Android library、繼承 `GodotPlugin` 並帶 Godot manifest metadata。正確的共用點是更底層的「純 Android WebView backend AAR」，由 Unity 與 Godot 各自的薄 wrapper 依賴。

#### Unity × iOS

- C# 端少量 `DllImport("__Internal")` 宣告可與 Unity adapter 同一 C# target（邏輯上仍放 `bindings/ios`）。
- Objective-C/Objective-C++、`.a` / `.xcframework` 或 Xcode integration 必須是獨立 Bazel native target，因為 Unity iOS 是 static integration，且需 C linkage／Xcode 複製規則。[Unity 2021.3：Building plug-ins for iOS](https://docs.unity3d.com/2021.3/Documentation/Manual/PluginsForIOS.html)
- 仍應放進同一 Unity UPM 發佈物，由 importer 標為 iOS-only。

#### Unity × Windows 11 / WebView2

- 若 Unity C# 只 P/Invoke 一個穩定 C ABI，宣告可與 adapter 同一 C# target。
- Win32 WebView2 implementation／loader 必須獨立 C++ target；WebView2 的 Win32 API 使用 WebView2 SDK/headers，建立 environment/controller，且 loader 可為 architecture-specific DLL。[Microsoft：Get started with WebView2 in Win32](https://learn.microsoft.com/en-us/microsoft-edge/webview2/get-started/win32)；[Microsoft：WebView2 distribution](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)
- Windows 11 隨附 Evergreen Runtime，但官方仍建議建立 WebView2 前檢查 Runtime；這屬 platform backend／installer 責任，不應進 Unity adapter。[Microsoft：WebView2 distribution](https://learn.microsoft.com/en-us/microsoft-edge/webview2/concepts/distribution)

#### Unity Web / iframe

- Unity C# facade 可以不另拆 target；Web-only extern 宣告保持 internal。
- `.jslib` 必須作為獨立 build/package input 處理，但可留在同一 UPM artefact。Unity 官方要求透過 JavaScript plugin 與 browser scripting 互動。[Unity：Interaction with browser scripting](https://docs.unity3d.com/Manual/webgl-interactingwithbrowserscripting.html)
- iframe 建立、DOM positioning、關閉與釋放應抽成共用 `webview-web` JS core；Unity `.jslib` 只轉接。這是根據官方入口機制做出的架構推論。

### Godot（目前穩定版）

#### Godot adapter 本身

建議用一個 addon facade 對外暴露一致 API。若 facade 是 GDScript，可在同一 script target／addon 中使用 engine singleton 或 `OS.has_feature()` 路由；Godot feature tags 本來就用於辨識 platform、architecture、debug/release，也用來決定 GDExtension library 載入。[Godot：Feature tags](https://docs.godotengine.org/en/stable/tutorials/export/feature_tags.html)

若 facade 選 C#，要先注意 Godot 官方文件仍把 Android/iOS C# export 列為 experimental，且 Godot 4 C# 目前不能 export Web；因此本專案若要求所有平台一致，**GDScript facade 或 GDExtension facade 比單一 C# facade 更可行**。[Godot：Exporting for Android](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_android.html)；[Godot：Exporting for iOS](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_ios.html)；[Godot：Exporting for Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)

#### Godot × Android

- Godot Android v2 plugin 必須是獨立 Android/AAR target：它是依賴 Godot Android library、包含 custom manifest、由 `GodotPlugin` hook engine lifecycle 的 Android library；並要求 Gradle build process。[Godot：Android plugins](https://docs.godotengine.org/en/stable/tutorials/platform/android/android_plugin.html)
- GDScript facade／wrapper 可留在主 adapter target／addon；官方也建議提供 wrapper class 簡化已暴露 Java/Kotlin API 的使用。
- AAR、export script、`plugin.cfg` 與可選 `.gdextension` 仍可一起裝進同一 Godot addon 發佈物。

#### Godot × iOS

- iOS plugin native target 必須獨立：Godot iOS plugin 是 `.a` 或包含 static libraries 的 `.xcframework`，依賴 Godot headers，另帶 `.gdip` 設定；這與 GDScript adapter 不是同一 build action。[Godot：Creating iOS plugins](https://docs.godotengine.org/en/stable/tutorials/platform/ios/ios_plugin.html)
- facade/wrapper 可與 adapter 同 target／addon；native binary 與 `.gdip` 留在同一發佈物。

#### Godot × Windows 11 / WebView2

- 若採單一 GDExtension C++ library，Godot adapter glue 與 Windows binding **可以是同一 DLL target**，前提是該 target 只建 Windows、直接連結獨立 `webview-windows` backend，且沒有其他平台共用這個 adapter binary。
- 若希望同一 Godot adapter source 對多平台產出，則把 GDExtension adapter 與 Windows WebView2 binding 分 targets；`.gdextension` 可依 feature flags 選擇各平台 binary。[Godot：The `.gdextension` file](https://docs.godotengine.org/en/stable/tutorials/scripting/gdextension/gdextension_file.html)
- WebView2 loader 的 architecture-specific 配送仍是獨立 Windows backend/binary concern，不應混入 Godot facade。

#### Godot Web / iframe

- 若 facade 是 GDScript，少量 `JavaScriptBridge` 呼叫可以和 adapter 同 target／addon，不需 GDExtension binary；該 singleton 官方明確只在 Web export 實作。[Godot：JavaScriptBridge](https://docs.godotengine.org/en/stable/classes/class_javascriptbridge.html)
- 共用 iframe DOM 邏輯放 `webview-web` JS core；Godot binding 只取得 global interface 並呼叫它。這與 Unity `.jslib` 是兩個入口，但可共用同一 JS core。
- 若改用 Web GDExtension/Wasm，就必須另建 Emscripten/Wasm target，而且 Godot export 必須啟用 Extension Support。[Godot：Exporting for Web](https://docs.godotengine.org/en/stable/tutorials/export/exporting_for_web.html)

## 5. 適合本專案的判準表

在新增任何 `webview-<engine>-<platform>` 實體模組前，依序套用下表；第一個「是」通常就決定最小拆分層級。

| 問題 | 是 | 否 |
|---|---|---|
| 是否由不同引擎套件系統消費？ | 至少拆發佈物：Unity UPM 與 Godot addon 不合併 | 下一題 |
| 是否使用不同 Bazel rule kind、toolchain 或 link mode？ | 拆 target；可留同 package/發佈物 | 下一題 |
| 是否產出獨立 AAR、`.a`/`.xcframework`、DLL、Wasm、`.jslib` payload？ | 拆 target；由 engine package 聚合 | 下一題 |
| 是否帶引擎專屬 compile dependency、manifest metadata 或 entry point？ | 拆 engine × platform binding target | 下一題 |
| 是否需要不同 CPU/ABI matrix？ | 拆 target 或每架構子 target，最上層用 select/alias 聚合 | 下一題 |
| 是否需要獨立裝置／host 測試環境？ | 拆 testable target | 下一題 |
| 是否只有少量同語言呼叫宣告／路由，且平台 deps 能完全隔離？ | 可與 engine adapter 同 target；保留內部邏輯分區 | 下一題 |
| 是否需要不同 public visibility？ | 拆 target；通常不用拆 package | 下一題 |
| 是否可由使用者獨立安裝、版本化或移除？ | 才考慮獨立發佈 artefact／package | 保持單一 engine 發佈物 |
| 是否只有「概念上責任不同」這一個理由？ | 不拆實體模組；以目錄、namespace、interface、tests 表達 | — |

## 6. 建議的初始實體配置

```text
packages/
├── webview-core/                 # 公開契約與狀態語意
├── webview-android/              # 純 Android backend；不依賴 Unity/Godot
├── webview-ios/                  # 純 iOS backend；不依賴 Unity/Godot
├── webview-windows/              # 純 Win32/WebView2 backend
├── webview-web/                  # 共用 iframe/DOM JavaScript core
├── webview-unity/                # 一個 Bazel package + 一個 UPM 發佈物
│   └── src/
│       ├── adapter/
│       └── bindings/{android,ios,windows,web}/
└── webview-godot/                # 一個 Bazel package + 一個 Godot addon 發佈物
    └── src/
        ├── adapter/
        └── bindings/{android,ios,windows,web}/
```

同一 `BUILD.bazel` 內先採下列 target 粒度（名稱僅示意）：

- Unity：`:adapter_cs`；`:android_aar`（只有需要自有 Java/Kotlin wrapper 時）；`:ios_native`；`:windows_native`；`:web_jslib`；`:upm_package`。
- Godot：`:adapter`；`:android_aar_plugin`；`:ios_plugin`；`:windows_gdextension`；`:web_bridge`（若純 GDScript 可併 `:adapter`）；`:godot_addon`。

其中 `:upm_package` / `:godot_addon` 是聚合發佈 targets，不代表其內部只有一個 binary target。這個配置把「最大化共用」落在 platform backend 與 WebView Core，同時把不可避免的引擎入口縮成薄 binding。

## 7. 需要 Wayfinder 另立決策的相容性阻塞

Android 需求必須先修正，否則後續任何 module matrix 都會建立在不可實現的共同基線上：

- Unity 2021.3：最低 Android 5.1 / API 22。[官方文件](https://docs.unity3d.com/2021.3/Documentation/Manual/android-requirements-and-compatibility.html)
- 目前 stable Godot：exported native project 的最低 Android 7.0（Compatibility），Forward+/Mobile 最低 Android 9.0。[官方文件](https://docs.godotengine.org/en/stable/about/system_requirements.html)

建議把支援矩陣改寫為「每個引擎支援其官方最低 OS 或更高」，或明確鎖定特定舊 Godot／Unity 版本後重新驗證。不要用自行降低 `minSdk` 視為官方支援；能編譯不等於引擎官方支援。

## 最終判斷

對本專案而言，「Engine Adapter 與 Binding/Composition 不拆實體模組」最精確的答案是：

- **不拆 Bazel package：預設成立。** 同一引擎的一切 adapter/bindings 先放同一 package。
- **不拆 Bazel target：只對同語言、同 toolchain、沒有獨立 payload 的薄 binding 成立。** Unity C# P/Invoke/JNI 宣告與 Godot GDScript Web bridge 是主要候選。
- **不拆發佈物：預設成立。** 每個引擎各一個完整 SDK 發佈物，內含平台選擇後的 payload。
- Android AAR、iOS native plugin、Windows WebView2 native binary、Unity `.jslib`／可選 Godot Web Wasm 等，因 build action 或載入機制不同，應拆 target；但它們仍不需要升格成獨立 repo module 或獨立使用者安裝包。

這樣保留了第 3、4 層的邏輯清晰度，又避免把每個引擎 × 平台組合都擴張成對外模組。
