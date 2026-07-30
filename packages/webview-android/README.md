# Android Platform Backend

Canonical Android Platform Backend Repository Module. Engine-specific Android
integration belongs to Binding Targets, not this module.

The canonical `:backend` target exposes the repository-wide `PlatformBackendInfo`
contract and an Android AAR payload. The AAR owns the asynchronous Java 11
`AndroidPlatformBackend`, resolves a non-owning host capability on the UI thread,
and maintains the application-wide one-Surface lease. Binding Targets provide the
current `ViewGroup` locator and translate Core commands and completions.

Supported payload profiles:

- `release/arm64-v8a/verve-webview.aar`
- `verification/x86_64/verve-webview.aar`

The AAR itself is architecture-neutral Java bytecode; the distinct payload keys
make the supported release and verification profiles explicit to later Binding
selection.

Verification targets:

- `//packages/webview-android:backend_unit_test` exercises the serialized
  lifecycle, host loss, stale generations, lease rollback, geometry, and URL
  policy without an Android device.
- `//packages/webview-android:backend_contract` verifies the canonical provider,
  AAR members, minSdk 24, and Java 11 bytecode.
- `//packages/webview-android:backend_instrumented_test` builds an instrumentation
  APK that checks real WebView settings, navigation containment, geometry,
  cleanup, and host-loss behavior on an API 24+ device.
