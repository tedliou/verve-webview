extends Control

const WebViewType = preload("res://addons/verve_webview/webview.gd")
const OptionsType = preload("res://addons/verve_webview/webview_options.gd")

var web_view: RefCounted
var rectangle := Rect2(40, 80, 640, 360)
var status_label := Label.new()


func _ready() -> void:
	var operations := [
		["Initialize", initialize],
		["Open", open],
		["Navigate", navigate],
		["Rectangle", update_rectangle],
		["Close", close],
		["Reopen", reopen],
		["Dispose", dispose],
	]
	var row := HBoxContainer.new()
	add_child(row)
	for item in operations:
		var button := Button.new()
		button.text = item[0]
		button.pressed.connect(item[1])
		row.add_child(button)
	status_label.text = "Ready / visible error reporting"
	status_label.position = Vector2(0, 48)
	add_child(status_label)


func initialize() -> void:
	web_view = WebViewType.new()
	report("initialize", await web_view.initialize(OptionsType.new()))


func open() -> void:
	if web_view == null:
		show_error("initialize first")
		return
	report("open", await web_view.open("https://example.com/", rectangle))


func navigate() -> void:
	report("navigate", await web_view.open("https://www.example.com/", rectangle))


func update_rectangle() -> void:
	rectangle = Rect2(80, 120, 520, 300)
	report(
		"rectangle",
		await web_view.open("https://www.example.com/?rectangle=updated", rectangle)
	)


func close() -> void:
	if web_view == null:
		show_error("initialize first")
		return
	report("close", await web_view.close())


func reopen() -> void:
	await close()
	report("reopen", await web_view.open("https://example.com/?reopen=true", rectangle))


func dispose() -> void:
	if web_view == null:
		show_error("initialize first")
		return
	report("dispose", await web_view.dispose())


func report(operation: String, result: RefCounted) -> void:
	if result.is_success:
		status_label.text = operation + ": ok"
	else:
		show_error(
			"%s: %s: %s" % [operation, result.code, result.diagnostic_detail]
		)
	print(status_label.text)


func show_error(message: String) -> void:
	status_label.text = "error: " + message
	push_error(status_label.text)
