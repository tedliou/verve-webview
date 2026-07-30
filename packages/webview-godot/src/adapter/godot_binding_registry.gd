extends RefCounted

## Composition seam used by a platform-selected Binding Target.
##
## The registry retains the Host Locator capability, but a bridge must treat
## each located host as borrowed: resolve it on the Godot main thread for each
## operation and never retain or release the returned host.

static var _host_locator: RefCounted
static var _bridge_factory: Callable


static func install(host_locator: RefCounted, bridge_factory: Callable) -> void:
	if host_locator == null:
		push_error("Godot Binding Target must provide a Host Locator.")
		return
	if not bridge_factory.is_valid():
		push_error("Godot Binding Target must provide a bridge factory.")
		return
	if _bridge_factory.is_valid():
		push_error("A Godot Binding Target is already installed.")
		return
	_host_locator = host_locator
	_bridge_factory = bridge_factory


static func create_or_missing() -> RefCounted:
	if not _bridge_factory.is_valid() or _host_locator == null:
		var environment = load(
			"res://addons/verve_webview/godot_environment.gd"
		)
		return environment.MissingBindingBridge.new()
	var bridge: Variant = _bridge_factory.call(_host_locator)
	if bridge == null:
		push_error("The Godot Binding Target returned no bridge.")
		var environment = load(
			"res://addons/verve_webview/godot_environment.gd"
		)
		return environment.MissingBindingBridge.new()
	return bridge
