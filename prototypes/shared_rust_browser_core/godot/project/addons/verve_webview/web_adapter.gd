class_name VerveWebViewWebPrototype
extends RefCounted

# PROTOTYPE ONLY: thin Godot transport. Callback objects are retained fields.
var _core: JavaScriptObject
var _ready_callback: JavaScriptObject
var _error_callback: JavaScriptObject
var _event_callback: JavaScriptObject
var _completed: Callable
var _event_sink: Callable

func initialize(wasm_url: String, completed: Callable, event_sink: Callable) -> void:
	_completed = completed
	_event_sink = event_sink
	_core = JavaScriptBridge.get_interface("VerveWebViewCore")
	if _core == null:
		_completed.call("{\"ok\":false,\"code\":\"facade_missing\"}")
		return
	_event_callback = JavaScriptBridge.create_callback(_on_event)
	_ready_callback = JavaScriptBridge.create_callback(_on_ready)
	_error_callback = JavaScriptBridge.create_callback(_on_error)
	_core.setEventSink(_event_callback)
	var promise: JavaScriptObject = _core.ready(wasm_url)
	promise.then(_ready_callback).catch(_error_callback)

func create_instance() -> String:
	return str(_core.createInstance())

func request(operation: String, handle: int, payload_json := "{}") -> String:
	return str(_core.request(operation, handle, payload_json))

func prototype_trap() -> String:
	return str(_core.prototypeTrap())

func prototype_phase() -> String:
	return str(_core.prototypePhase())

func _on_ready(arguments: Array) -> void:
	_completed.call(str(arguments[0]))

func _on_error(arguments: Array) -> void:
	var error: JavaScriptObject = arguments[0]
	_completed.call(str(error.message))

func _on_event(arguments: Array) -> void:
	_event_sink.call(str(arguments[0]))
