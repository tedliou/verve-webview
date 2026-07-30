@tool
extends EditorPlugin

var _android_export_plugin: EditorExportPlugin
var _web_export_plugin: EditorExportPlugin


func _enter_tree() -> void:
	_android_export_plugin = preload("export/android_export_plugin.gd").new()
	_web_export_plugin = preload("export/web_export_plugin.gd").new()
	add_export_plugin(_android_export_plugin)
	add_export_plugin(_web_export_plugin)


func _exit_tree() -> void:
	remove_export_plugin(_web_export_plugin)
	remove_export_plugin(_android_export_plugin)
	_web_export_plugin = null
	_android_export_plugin = null
