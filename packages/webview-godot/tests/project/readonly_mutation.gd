extends SceneTree

const WebViewResultType = preload(
	"res://addons/verve_webview/webview_contract.gd"
)


func _init() -> void:
	var result := WebViewResultType.new(WebViewResultType.ErrorCode.OK, "original")
	result.code = WebViewResultType.ErrorCode.INVALID_URL
	result.diagnostic_detail = "mutated"
	result.is_success = false
	if (
		result.code != WebViewResultType.ErrorCode.OK
		or result.diagnostic_detail != "original"
		or not result.is_success
	):
		push_error("WebViewResult mutation changed a read-only value")
		quit(1)
	else:
		print("ISSUE29_GODOT_IMMUTABLE_RESULT_OK")
		quit(0)
