extends RefCounted

const WebViewResultType = preload(
	"res://addons/verve_webview/webview_contract.gd"
)


class MainThreadScheduler extends RefCounted:
	func post(action: Callable) -> void:
		action.call_deferred()


class ViewportSize extends RefCounted:
	func get_size() -> Vector2:
		var main_loop := Engine.get_main_loop()
		if not main_loop is SceneTree:
			return Vector2.ZERO
		return main_loop.root.get_visible_rect().size


class UnsupportedEnvironmentBridge extends RefCounted:
	signal completed(operation: int, wire_code: int, diagnostic: String)

	const DETAIL := "Verve WebView is unavailable in this Godot environment."
	var _disposed := false

	func initialize(_options: RefCounted) -> Dictionary:
		return _disposed_result() if _disposed else _unsupported()

	func open(_url: String, _geometry: Dictionary) -> Dictionary:
		return _disposed_result() if _disposed else _not_initialized()

	func close() -> Dictionary:
		return _disposed_result() if _disposed else _not_initialized()

	func dispose() -> Dictionary:
		if _disposed:
			return _disposed_result()
		_disposed = true
		return _rejected(WebViewResultType.ErrorCode.OK)

	func _unsupported() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.UNSUPPORTED_ENVIRONMENT, DETAIL)

	func _not_initialized() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.NOT_INITIALIZED)

	func _disposed_result() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.DISPOSED)

	func _rejected(wire_code: int, diagnostic := "") -> Dictionary:
		return {
			"accepted": false,
			"operation": 0,
			"wire_code": wire_code,
			"diagnostic": diagnostic,
		}


class MissingBindingBridge extends RefCounted:
	signal completed(operation: int, wire_code: int, diagnostic: String)

	const DETAIL := "The required Godot Binding Target is not installed."
	var _disposed := false

	func initialize(_options: RefCounted) -> Dictionary:
		return _disposed_result() if _disposed else _missing()

	func open(_url: String, _geometry: Dictionary) -> Dictionary:
		return _disposed_result() if _disposed else _not_initialized()

	func close() -> Dictionary:
		return _disposed_result() if _disposed else _not_initialized()

	func dispose() -> Dictionary:
		if _disposed:
			return _disposed_result()
		_disposed = true
		return _rejected(WebViewResultType.ErrorCode.OK)

	func _missing() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.DISTRIBUTION_INVALID, DETAIL)

	func _not_initialized() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.NOT_INITIALIZED)

	func _disposed_result() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.DISPOSED)

	func _rejected(wire_code: int, diagnostic := "") -> Dictionary:
		return {
			"accepted": false,
			"operation": 0,
			"wire_code": wire_code,
			"diagnostic": diagnostic,
		}


static func is_supported() -> bool:
	return (
		OS.has_feature("android")
		or OS.has_feature("ios")
		or OS.has_feature("windows")
		or OS.has_feature("web")
	)
