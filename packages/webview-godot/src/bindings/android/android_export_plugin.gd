@tool
extends EditorExportPlugin

const PLUGIN_NAME := "VerveWebView"
const PLUGIN_AARS := PackedStringArray([
	"verve_webview/bin/android/verve-webview-godot.aar",
	"verve_webview/bin/android/verve-webview-backend.aar",
])


func _get_name() -> String:
	return PLUGIN_NAME


func _supports_platform(platform: EditorExportPlatform) -> bool:
	return platform is EditorExportPlatformAndroid


func _get_android_libraries(
		_platform: EditorExportPlatform,
		_debug: bool
) -> PackedStringArray:
	return PLUGIN_AARS
