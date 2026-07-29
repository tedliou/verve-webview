# Unity Engine Adapter

The generated Unity API exposes `WebViewErrorCode` and immutable
`WebViewResult`. `WebView` presents the four caller operations as
`Task<WebViewResult>`:

```csharp
var webView = new WebView();
WebViewResult result = await webView.InitializeAsync(WebViewOptions.Default);
result = await webView.OpenAsync("https://example.test");
result = await webView.CloseAsync();
result = await webView.DisposeAsync();
```

Expected lifecycle, validation, transport, and Backend failures complete the
Task normally. Accepted completions are de-duplicated by opaque operation
identity and marshalled onto the captured Unity main-thread synchronization
context. Dispose is terminal and completes a retired caller Task with
`Disposed`; a late retired Core completion is ignored.

Unity pixel rectangles use the engine's bottom-left origin. The Adapter converts
them to normalized top-left geometry relative to the complete game view before
crossing the Binding seam. A selected Binding Target registers one
`IWebViewBridge` factory and `IUnityHostLocator` capability. The locator is
passed to each bridge without being resolved by the Adapter; a located host is
borrowed for one platform UI operation and must never be retained or released.

The Editor always selects a deterministic asynchronous fake. A supported Player
without its required Binding Target reports `DistributionInvalid`; other Unity
environments report `UnsupportedEnvironment`. Concrete Android, iOS, Windows,
and Web composition remains in the four fixed Binding Targets.

Run the pinned Unity 2021.3 EditMode contract through Unity CLI:

```sh
packages/webview-unity/tests/run_editmode_tests.sh
```
