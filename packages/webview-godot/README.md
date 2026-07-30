# Godot Engine Adapter

Owns the Godot Engine Adapter, its four fixed Binding Targets, and the single
release-only Godot Engine SDK Distribution target.

The caller-facing API is a source-only GDScript facade:

```gdscript
var web_view := WebView.new()
var result: WebViewResult = await web_view.initialize(WebViewOptions.new())
result = await web_view.open("https://example.test", Rect2(20, 10, 400, 300))
result = await web_view.close()
result = await web_view.dispose()
```

Expected lifecycle, validation, Backend, ABI, and distribution failures return
`WebViewResult` normally. `code`, `diagnostic_detail`, and derived `is_success`
are read-only. Error enum members are generated uppercase spellings with stable
wire IDs.

Binding Targets install the internal `GodotBindingRegistry` composition seam.
The Adapter depends on no concrete Platform Backend. A Binding Target receives
a non-owning Host Locator capability and resolves the current host on the Godot
main thread for every operation; located hosts, Core handles, operation IDs, and
event transport never enter the public API.
