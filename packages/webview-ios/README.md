# iOS Platform Backend

Canonical iOS Platform Backend Repository Module. Engine-specific iOS
integration belongs to Binding Targets, not this module.

The canonical `:backend` target exposes the repository-wide
`PlatformBackendInfo` contract and a static `VerveWebViewIOS.xcframework`.
`rules_apple` 4.5.3 owns the device `arm64` and simulator `arm64`/`x86_64`
slices with iOS 13.0 as the minimum.

The Objective-C++ Backend owns WKWebView creation and destruction, dispatches
accepted work to the main thread, resolves the non-owning Host Locator for every
UI operation, reapplies normalized geometry after host layout, and coordinates
the application-wide Surface Lease. It exposes only lifecycle commands,
asynchronous completion, `host_lost`, and diagnostics.

The fixed browser policy accepts only credential-free absolute HTTP(S) URLs,
keeps top-level navigation inside one Surface, cancels popups, downloads,
deprecated TLS, and certificate failures, and registers no page-accessible
script message handler. It denies media/motion permissions through the public
iOS 15+ delegates and file selection through the public iOS 18.4+ delegate.
Normal first-party cookies use WebKit's persistent data store. On earlier OS
versions, and wherever WebKit has no public per-view override, the Backend
retains the user-mediated platform default and emits diagnostics instead of
using private API or weakening browser isolation silently.

Verification targets:

- `//packages/webview-ios:backend_unit_test` runs the portable lifecycle seam
  through seven deterministic host, geometry, lease, cleanup, URL-policy, and
  stale-generation scenarios.
- `//packages/webview-ios:backend_device_test` exercises a real WKWebView on an
  iOS simulator/device, including asynchronous lifecycle, normalized geometry,
  policy configuration, cleanup, and host loss.
- `//packages/webview-ios:backend_contract` verifies the canonical provider,
  runtime metadata, public header, and all device/simulator XCFramework slices.
