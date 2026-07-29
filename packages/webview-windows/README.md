# Windows Platform Backend

Canonical Windows 11 x86_64 WebView2 Platform Backend Repository Module.

The `:backend` target exposes `PlatformBackendInfo` and a real
`verve_webview_windows.dll`. It pins the release WebView2 SDK NuGet package,
statically links `WebView2Loader`, and discovers only an installed Evergreen
Runtime (minimum `86.0.616.0`); it never bundles or installs a Runtime.

The exported C ABI accepts lifecycle commands and reports asynchronous
completions plus `host_lost`. The Binding Target supplies a non-owning current
`HWND` locator and Windows UI dispatcher. The Backend owns environment,
controller, Surface Lease, normalized-to-DIP geometry, focus, host monitoring,
cleanup, and generation rollback.

Web content is always untrusted. The driver registers no host object or Web
message bridge; it rejects non-HTTP(S) navigation, popups, external URI
launches, permissions, downloads, client certificates, and TLS certificate
errors. Release callers pass `debugging_enabled=0`.
