class_name WebView
extends RefCounted

const WebViewResultType = preload(
	"res://addons/verve_webview/webview_contract.gd"
)
const DiagnosticDetail = preload(
	"res://addons/verve_webview/diagnostic_detail.gd"
)
const GeometryConverter = preload(
	"res://addons/verve_webview/geometry_converter.gd"
)
const GodotEnvironment = preload(
	"res://addons/verve_webview/godot_environment.gd"
)
const BindingRegistry = preload(
	"res://addons/verve_webview/godot_binding_registry.gd"
)


class PendingResult extends RefCounted:
	signal completed(result: RefCounted)

	var _resolved := false
	var disconnect_after := false

	func resolve(result: RefCounted) -> void:
		if _resolved:
			return
		_resolved = true
		completed.emit(result)


var _bridge: RefCounted
var _main_thread: RefCounted
var _viewport: RefCounted
var _gate := Mutex.new()
var _pending: Dictionary = {}
var _early_completions: Dictionary = {}
var _deliveries: Dictionary = {}
var _starts_in_progress := 0


func _init() -> void:
	_configure()


static func _create_for_testing(
	bridge_override: RefCounted,
	main_thread: RefCounted = null,
	viewport: RefCounted = null,
	supported_environment: Variant = null
) -> RefCounted:
	var script = load("res://addons/verve_webview/webview.gd")
	var instance: RefCounted = script.new()
	instance._bridge.completed.disconnect(instance._on_bridge_completed)
	instance._configure(
		bridge_override,
		main_thread,
		viewport,
		supported_environment
	)
	return instance


func _configure(
	bridge_override: RefCounted = null,
	main_thread: RefCounted = null,
	viewport: RefCounted = null,
	supported_environment: Variant = null
) -> void:
	_main_thread = (
		main_thread
		if main_thread != null
		else GodotEnvironment.MainThreadScheduler.new()
	)
	_viewport = viewport if viewport != null else GodotEnvironment.ViewportSize.new()
	var supported := (
		GodotEnvironment.is_supported()
		if supported_environment == null
		else bool(supported_environment)
	)
	if bridge_override != null:
		_bridge = bridge_override
	elif supported:
		_bridge = BindingRegistry.create_or_missing()
	else:
		_bridge = GodotEnvironment.UnsupportedEnvironmentBridge.new()
	_bridge.completed.connect(_on_bridge_completed)


func initialize(options: RefCounted = null) -> Signal:
	if options == null:
		return _completed_result(WebViewResultType.ErrorCode.INVALID_OPTIONS)
	return _begin(_bridge.initialize.bind(options), false)


func open(url: String, rectangle: Variant = null) -> Signal:
	if url.is_empty():
		return _completed_result(WebViewResultType.ErrorCode.INVALID_URL)
	var geometry := GeometryConverter.full_screen()
	if rectangle != null:
		if not rectangle is Rect2:
			return _completed_result(WebViewResultType.ErrorCode.INVALID_GEOMETRY)
		geometry = GeometryConverter.from_godot_rect(rectangle, _viewport.get_size())
	return _begin(_bridge.open.bind(url, geometry), false)


func close() -> Signal:
	return _begin(_bridge.close, false)


func dispose() -> Signal:
	return _begin(_bridge.dispose, true)


func _begin(start_operation: Callable, is_dispose: bool) -> Signal:
	var pending_result := PendingResult.new()
	pending_result.disconnect_after = is_dispose
	_gate.lock()
	_starts_in_progress += 1
	_gate.unlock()

	var start: Dictionary = start_operation.call()
	if not start.get("accepted", false):
		_gate.lock()
		_starts_in_progress -= 1
		if _starts_in_progress == 0:
			_early_completions.clear()
		_gate.unlock()
		_post_result(
			pending_result,
			_map_result(
				int(start.get("wire_code", WebViewResultType.ErrorCode.INTERNAL_FAILURE)),
				str(start.get("diagnostic", ""))
			)
		)
		return pending_result.completed

	var retired: Array = []
	var early: Variant = null
	var operation := int(start["operation"])
	_gate.lock()
	if is_dispose:
		retired.assign(_pending.values())
		_pending.clear()
	_pending[operation] = pending_result
	if _early_completions.has(operation):
		early = _early_completions[operation]
		_early_completions.erase(operation)
	_starts_in_progress -= 1
	if _starts_in_progress == 0:
		_early_completions.clear()
	_gate.unlock()

	for retired_result in retired:
		_post_result(
			retired_result,
			WebViewResultType.new(WebViewResultType.ErrorCode.DISPOSED)
		)
	if early != null:
		_complete_registered(early)
	return pending_result.completed


func _on_bridge_completed(operation: int, wire_code: int, diagnostic: String) -> void:
	var pending_result: Variant = null
	_gate.lock()
	if _pending.has(operation):
		pending_result = _pending[operation]
		_pending.erase(operation)
	elif _starts_in_progress > 0 and not _early_completions.has(operation):
		_early_completions[operation] = {
			"operation": operation,
			"wire_code": wire_code,
			"diagnostic": diagnostic,
		}
	_gate.unlock()
	if pending_result != null:
		_post_result(pending_result, _map_result(wire_code, diagnostic))


func _complete_registered(completion: Dictionary) -> void:
	var operation := int(completion["operation"])
	var pending_result: Variant = null
	_gate.lock()
	if _pending.has(operation):
		pending_result = _pending[operation]
		_pending.erase(operation)
	_gate.unlock()
	if pending_result != null:
		_post_result(
			pending_result,
			_map_result(int(completion["wire_code"]), str(completion["diagnostic"]))
		)


func _completed_result(code: int) -> Signal:
	var pending_result := PendingResult.new()
	_post_result(pending_result, WebViewResultType.new(code))
	return pending_result.completed


func _post_result(pending_result: PendingResult, result: RefCounted) -> void:
	var delivery := pending_result.get_instance_id()
	_gate.lock()
	_deliveries[delivery] = pending_result
	_gate.unlock()
	_main_thread.post(_deliver_result.bind(delivery, result))


func _deliver_result(delivery: int, result: RefCounted) -> void:
	var pending_result: Variant = null
	_gate.lock()
	if _deliveries.has(delivery):
		pending_result = _deliveries[delivery]
	_gate.unlock()
	if pending_result == null:
		return
	pending_result.resolve(result)
	if pending_result.disconnect_after and _bridge.completed.is_connected(_on_bridge_completed):
		_bridge.completed.disconnect(_on_bridge_completed)
	_gate.lock()
	_deliveries.erase(delivery)
	_gate.unlock()


static func _map_result(wire_code: int, diagnostic: String) -> RefCounted:
	if not wire_code in WebViewResultType.ErrorCode.values():
		return WebViewResultType.new(
			WebViewResultType.ErrorCode.ABI_MISMATCH,
			DiagnosticDetail.unknown_wire_code(wire_code, diagnostic)
		)
	return WebViewResultType.new(wire_code, DiagnosticDetail.normalize(diagnostic))
