@tool
extends EditorExportPlugin

# PROTOTYPE ONLY: package-owned export placement, no consumer HTML shell.
var _web_export_path := ""

func _get_name() -> String:
	return "VerveWebViewBrowserCorePrototype"

func _export_begin(features: PackedStringArray, _is_debug: bool, path: String, _flags: int) -> void:
	_web_export_path = path if features.has("web") else ""

func _export_end() -> void:
	if _web_export_path.is_empty():
		return

	var output_dir := _web_export_path.get_base_dir()
	var destination := output_dir.path_join("VerveWebViewCore")
	DirAccess.make_dir_recursive_absolute(destination)
	var source := ProjectSettings.globalize_path("res://addons/verve_webview/web")
	for file_name in [
		"verve_webview_core.js",
		"verve_webview_core_bg.wasm",
		"verve_webview_core_facade.js",
	]:
		var error := DirAccess.copy_absolute(
			source.path_join(file_name),
			destination.path_join(file_name)
		)
		if error != OK:
			push_error("VERVE_PROTOTYPE failed to copy %s: %s" % [file_name, error_string(error)])

	if not FileAccess.file_exists(_web_export_path):
		push_error("VERVE_PROTOTYPE export did not produce HTML: %s" % _web_export_path)
		return
	var index := FileAccess.open(_web_export_path, FileAccess.READ)
	if index == null:
		push_error("VERVE_PROTOTYPE cannot open exported HTML: %s" % _web_export_path)
		return
	var html := index.get_as_text()
	index.close()
	const MARKER := "<!-- VERVE_WEBVIEW_CORE_PROTOTYPE -->"
	if not html.contains(MARKER):
		var scripts := MARKER + "\n"
		scripts += "<script src=\"VerveWebViewCore/verve_webview_core.js\"></script>\n"
		scripts += "<script src=\"VerveWebViewCore/verve_webview_core_facade.js\"></script>\n"
		html = html.replace("</head>", scripts + "</head>")
		index = FileAccess.open(_web_export_path, FileAccess.WRITE)
		index.store_string(html)
		index.close()
	print("VERVE_PROTOTYPE Godot browser Core staged at %s" % destination)
