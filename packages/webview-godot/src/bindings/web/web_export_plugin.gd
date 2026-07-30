@tool
extends EditorExportPlugin

const MARKER := "<!-- VERVE_WEBVIEW_CORE -->"
const PAYLOADS := [
	"api-contract.js",
	"verve_webview_core.js",
	"verve_webview_core_bg.wasm",
	"verve_webview_core_facade.js",
	"verve_webview_web_backend.js",
]

var _web_export_path := ""


func _get_name() -> String:
	return "VerveWebViewBrowserCore"


func _supports_platform(platform: EditorExportPlatform) -> bool:
	return platform is EditorExportPlatformWeb


func _export_begin(
		features: PackedStringArray,
		_is_debug: bool,
		path: String,
		_flags: int
) -> void:
	_web_export_path = path if features.has("web") else ""


func _export_end() -> void:
	if _web_export_path.is_empty():
		return
	var output_dir := _web_export_path.get_base_dir()
	var destination := output_dir.path_join("VerveWebViewCore")
	var source := ProjectSettings.globalize_path(
		"res://addons/verve_webview/bin/web"
	)
	DirAccess.make_dir_recursive_absolute(destination)
	for file_name in PAYLOADS:
		var error := DirAccess.copy_absolute(
			source.path_join(file_name),
			destination.path_join(file_name)
		)
		if error != OK:
			push_error(
				"Verve WebView failed to stage %s: %s"
				% [file_name, error_string(error)]
			)
	if not FileAccess.file_exists(_web_export_path):
		push_error("Verve WebView export HTML is missing: %s" % _web_export_path)
		return
	var index := FileAccess.open(_web_export_path, FileAccess.READ)
	if index == null:
		push_error("Verve WebView cannot read export HTML: %s" % _web_export_path)
		return
	var html := index.get_as_text()
	index.close()
	if html.contains(MARKER):
		return
	var scripts := MARKER + "\n"
	for file_name in [
		"api-contract.js",
		"verve_webview_core.js",
		"verve_webview_core_facade.js",
		"verve_webview_web_backend.js",
	]:
		scripts += (
			"<script src=\"VerveWebViewCore/%s\"></script>\n" % file_name
		)
	html = html.replace("</head>", scripts + "</head>")
	index = FileAccess.open(_web_export_path, FileAccess.WRITE)
	if index == null:
		push_error("Verve WebView cannot update export HTML: %s" % _web_export_path)
		return
	index.store_string(html)
	index.close()
