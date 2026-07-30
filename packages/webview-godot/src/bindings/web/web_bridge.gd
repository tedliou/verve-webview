class_name VerveWebViewBrowserCore
extends RefCounted

var _core: JavaScriptObject
var _ready_callback: JavaScriptObject
var _error_callback: JavaScriptObject
var _event_callback: JavaScriptObject


func initialize(completed: Callable, event_sink: Callable) -> void:
	_core = JavaScriptBridge.get_interface("VerveWebViewCore")
	if _core == null:
		completed.call("{\"ok\":false,\"code\":\"core_load_failed\"}")
		return
	_event_callback = JavaScriptBridge.create_callback(
		func(arguments: Array) -> void: event_sink.call(str(arguments[0]))
	)
	_ready_callback = JavaScriptBridge.create_callback(
		func(arguments: Array) -> void: completed.call(str(arguments[0]))
	)
	_error_callback = JavaScriptBridge.create_callback(
		func(arguments: Array) -> void: completed.call(str(arguments[0]))
	)
	_core.setEventSink(_event_callback)
	var promise: JavaScriptObject = _core.ready(
		"VerveWebViewCore/verve_webview_core_bg.wasm"
	)
	promise.then(_ready_callback).catch(_error_callback)
