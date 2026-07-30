# Web Platform Backend

Canonical Web Runtime Platform Backend Repository Module.

The `:backend` target exposes `PlatformBackendInfo` with the byte-identical Web
Core bundle plus `verve_webview_web_backend.js`. Engine Binding Targets install
the runtime only through the stable `VerveWebViewCore` facade:

```js
const backend = VerveWebViewWebBackend.install({
  core: VerveWebViewCore,
  locateHost: () => document.getElementById("engine-game-view"),
});
```

`locateHost` is a non-owning Host Locator. The Backend invokes it asynchronously
on the browser main loop whenever it needs the current DOM host; it does not
retain a host capability across operations.

One application-wide Surface Lease permits one iframe WebView Surface. The
Surface uses normalized geometry relative to the full host rectangle, responds
to host/window layout changes, receives focus on open, and is destroyed on
close, dispose, or permanent host loss. Permanent host loss is reported through
`VerveWebViewCore.reportHostLost`, returning the SDK Instance to
initialized/closed so a later open can resolve a replacement host.

All loaded documents are Untrusted Web Content. The outer iframe has exactly
`allow-scripts allow-forms`; it intentionally omits same-origin, top
navigation, popups, downloads, and device permissions. Direct Backend
navigation accepts only credential-free absolute HTTP(S) URLs as defense in
depth after Web Core validation. Browser same-origin rules make cross-origin
redirect destinations unobservable; the strict sandbox remains the enforcement
boundary for top navigation and new browsing contexts.

Run the real-browser contract:

```sh
bazel test //packages/webview-web:web_runtime_test --lockfile_mode=error
```
