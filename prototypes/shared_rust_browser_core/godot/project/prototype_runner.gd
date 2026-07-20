extends Node

var _adapter := VerveWebViewWebPrototype.new()
var _events: Array[String] = []
var _proof := {
	"engine": "godot",
	"phase": "",
	"init": "",
	"create": "",
	"open": "",
	"dispose": "",
	"disposedRequest": "",
	"lateCompletionEvents": -1,
	"trap": "",
}

func _ready() -> void:
	if not OS.has_feature("web"):
		push_error("VERVE_PROTOTYPE must run as a Web export")
		return
	_adapter.initialize(
		"VerveWebViewCore/verve_webview_core_bg.wasm",
		_on_initialized,
		func(value: String): _events.append(value)
	)

func _on_initialized(value: String) -> void:
	_proof.init = value
	_proof.phase = _adapter.prototype_phase()
	_proof.create = _adapter.create_instance()
	var created = JSON.parse_string(_proof.create)
	if created == null or not created.get("ok", false):
		_publish()
		return
	var handle: int = created.handle
	_proof.open = _adapter.request("open", handle, "{\"url\":\"https://example.invalid\"}")
	_proof.dispose = _adapter.request("dispose", handle)
	_proof.disposedRequest = _adapter.request("open", handle)
	await get_tree().process_frame
	await get_tree().process_frame
	_proof.lateCompletionEvents = _events.size()
	_proof.trap = _adapter.prototype_trap()
	_publish()

func _publish() -> void:
	var json := JSON.stringify(_proof)
	print("VERVE_PROTOTYPE_RESULT " + json)
	JavaScriptBridge.eval("""
		document.documentElement.setAttribute('data-verve-prototype-result', %s);
		let output = document.getElementById('verve-prototype-result');
		if (!output) {
			output = document.createElement('pre');
			output.id = 'verve-prototype-result';
			document.body.appendChild(output);
		}
		output.textContent = %s;
	""" % [JSON.stringify(json), JSON.stringify(json)], true)
