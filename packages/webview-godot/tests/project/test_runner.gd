extends SceneTree

const WebViewResultType = preload(
	"res://addons/verve_webview/webview_contract.gd"
)
const WebViewType = preload("res://addons/verve_webview/webview.gd")
const WebViewOptionsType = preload(
	"res://addons/verve_webview/webview_options.gd"
)

var _failures: Array[String] = []


class ControllableBridge extends RefCounted:
	signal completed(operation: int, wire_code: int, diagnostic: String)

	var next_operation := 1
	var last_geometry: Dictionary = {}
	var host_locator: RefCounted
	var host_resolution_count := 0

	func _init(locator: RefCounted = null) -> void:
		host_locator = locator

	func initialize(_options: RefCounted) -> Dictionary:
		_resolve_host()
		return _accept()

	func open(_url: String, geometry: Dictionary) -> Dictionary:
		_resolve_host()
		last_geometry = geometry
		return _accept()

	func close() -> Dictionary:
		_resolve_host()
		return _accept()

	func dispose() -> Dictionary:
		_resolve_host()
		return _accept()

	func complete_operation(operation: int, wire_code: int, diagnostic := "") -> void:
		completed.emit(operation, wire_code, diagnostic)

	func _accept() -> Dictionary:
		var operation := next_operation
		next_operation += 1
		return {
			"accepted": true,
			"operation": operation,
			"wire_code": 0,
			"diagnostic": "",
		}

	func _resolve_host() -> void:
		if host_locator != null:
			host_locator.locate_host()
			host_resolution_count += 1


class RejectingBridge extends RefCounted:
	signal completed(operation: int, wire_code: int, diagnostic: String)

	var wire_code: int
	var diagnostic: String

	func _init(code: int, detail := "") -> void:
		wire_code = code
		diagnostic = detail

	func initialize(_options: RefCounted) -> Dictionary:
		return _reject()

	func open(_url: String, _geometry: Dictionary) -> Dictionary:
		return _reject()

	func close() -> Dictionary:
		return _reject()

	func dispose() -> Dictionary:
		return _reject()

	func _reject() -> Dictionary:
		return {
			"accepted": false,
			"operation": 0,
			"wire_code": wire_code,
			"diagnostic": diagnostic,
		}


class EagerWorkerBridge extends RefCounted:
	signal completed(operation: int, wire_code: int, diagnostic: String)

	func initialize(_options: RefCounted) -> Dictionary:
		var worker := Thread.new()
		worker.start(
			func(): completed.emit(1, WebViewResultType.ErrorCode.OK, "")
		)
		worker.wait_to_finish()
		return {
			"accepted": true,
			"operation": 1,
			"wire_code": 0,
			"diagnostic": "",
		}

	func open(_url: String, _geometry: Dictionary) -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.NOT_INITIALIZED)

	func close() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.NOT_INITIALIZED)

	func dispose() -> Dictionary:
		return _rejected(WebViewResultType.ErrorCode.OK)

	func _rejected(wire_code: int) -> Dictionary:
		return {
			"accepted": false,
			"operation": 0,
			"wire_code": wire_code,
			"diagnostic": "",
		}


class QueueScheduler extends RefCounted:
	var _mutex := Mutex.new()
	var _queue: Array[Callable] = []
	var last_delivery_was_main_thread := false

	func post(action: Callable) -> void:
		_mutex.lock()
		_queue.append(action)
		_mutex.unlock()

	func pump() -> void:
		while true:
			_mutex.lock()
			if _queue.is_empty():
				_mutex.unlock()
				return
			var action: Callable = _queue.pop_front()
			_mutex.unlock()
			last_delivery_was_main_thread = Thread.is_main_thread()
			action.call()


class FixedViewport extends RefCounted:
	var size: Vector2

	func _init(value: Vector2) -> void:
		size = value

	func get_size() -> Vector2:
		return size


class CountingHostLocator extends RefCounted:
	var count := 0
	var _host: WeakRef

	func _init(host: RefCounted) -> void:
		_host = weakref(host)

	func locate_host() -> Variant:
		count += 1
		return _host.get_ref()


func _init() -> void:
	call_deferred("_run")


func _run() -> void:
	_test_generated_public_api_and_immutable_result()
	_test_four_lifecycle_methods_map_results()
	_test_godot_rect_normalizes_from_top_left()
	_test_expected_failure_and_unknown_wire_mapping()
	_test_dispose_preempts_pending_and_ignores_late_completion()
	_test_diagnostic_detail_is_safe_and_bounded()
	_test_worker_completion_is_delivered_on_main_thread()
	_test_worker_completion_before_bridge_returns_resolves_once()
	_test_host_locator_is_non_owning_and_resolved_per_operation()
	_test_unsupported_environment_is_deterministic()

	if _failures.is_empty():
		print("ISSUE29_GODOT_ADAPTER_TESTS_OK")
		quit(0)
	else:
		for failure in _failures:
			push_error(failure)
		quit(1)


func _test_four_lifecycle_methods_map_results() -> void:
	var scheduler := QueueScheduler.new()
	var bridge := ControllableBridge.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var results: Array = []
	var operations: Array[Callable] = [
		web_view.initialize.bind(WebViewOptionsType.new()),
		web_view.open.bind("https://example.test"),
		web_view.close,
		web_view.dispose,
	]
	for index in operations.size():
		var completion: Signal = operations[index].call()
		completion.connect(func(result): results.append(result))
		bridge.complete_operation(index + 1, WebViewResultType.ErrorCode.OK)
		scheduler.pump()
	_expect_equal(results.size(), 4, "all four lifecycle methods return mapped results")
	for result in results:
		_expect(result.is_success, "accepted lifecycle result is successful")


func _test_generated_public_api_and_immutable_result() -> void:
	var expected := {
		"OK": 0,
		"INVALID_OPTIONS": 100,
		"INVALID_URL": 101,
		"INVALID_GEOMETRY": 102,
		"NOT_INITIALIZED": 200,
		"ALREADY_INITIALIZED": 201,
		"OPERATION_IN_PROGRESS": 202,
		"DISPOSED": 203,
		"SURFACE_NOT_OPEN": 204,
		"SURFACE_IN_USE": 205,
		"HOST_UNAVAILABLE": 300,
		"HOST_LOST": 301,
		"BACKEND_FAILURE": 302,
		"CLEANUP_FAILED": 303,
		"CORE_LOAD_FAILED": 400,
		"ABI_MISMATCH": 401,
		"RUNTIME_UNAVAILABLE": 402,
		"UNSUPPORTED_ENVIRONMENT": 403,
		"DISTRIBUTION_INVALID": 404,
		"INTERNAL_FAILURE": 500,
	}
	_expect_equal(WebViewResultType.ErrorCode, expected, "generated uppercase error mapping")
	var result := WebViewResultType.new(WebViewResultType.ErrorCode.OK)
	_expect(result.is_success, "OK result must report success")
	_expect_equal(result.code, WebViewResultType.ErrorCode.OK, "read-only code remains unchanged")
	_expect_equal(result.diagnostic_detail, "", "read-only diagnostic has constructor value")
	var public_methods: Array[StringName] = []
	var init_argument_count := -1
	var public_instance = WebViewType.new()
	for method in public_instance.get_script().get_script_method_list():
		if method["name"] in [&"initialize", &"open", &"close", &"dispose"]:
			public_methods.append(method["name"])
		if method["name"] == &"_init":
			init_argument_count = method["args"].size()
	_expect_equal(public_methods.size(), 4, "WebView exposes four lifecycle methods")
	for expected_method in [&"initialize", &"open", &"close", &"dispose"]:
		_expect(expected_method in public_methods, "WebView exposes %s" % expected_method)
	_expect_equal(init_argument_count, 0, "WebView public constructor has no bridge arguments")


func _test_godot_rect_normalizes_from_top_left() -> void:
	var bridge := ControllableBridge.new()
	var scheduler := QueueScheduler.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var completion: Signal = web_view.open("https://example.test", Rect2(20, 10, 40, 30))
	var results: Array = []
	completion.connect(func(result): results.append(result))
	bridge.complete_operation(1, WebViewResultType.ErrorCode.OK)
	scheduler.pump()

	_expect_equal(results.size(), 1, "open resolves exactly once")
	_expect_approx(bridge.last_geometry["x"], 0.1, "normalized x")
	_expect_approx(bridge.last_geometry["y"], 0.1, "normalized top-left y")
	_expect_approx(bridge.last_geometry["width"], 0.2, "normalized width")
	_expect_approx(bridge.last_geometry["height"], 0.3, "normalized height")


func _test_expected_failure_and_unknown_wire_mapping() -> void:
	var scheduler := QueueScheduler.new()
	var bridge := ControllableBridge.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var completion: Signal = web_view.initialize(WebViewOptionsType.new())
	var results: Array = []
	completion.connect(func(result): results.append(result))
	bridge.complete_operation(1, 777, "received unknown wire code")
	scheduler.pump()

	_expect_equal(results.size(), 1, "unknown wire result resolves normally")
	_expect_equal(results[0].code, WebViewResultType.ErrorCode.ABI_MISMATCH, "unknown wire maps")
	_expect("777" in results[0].diagnostic_detail, "unknown wire diagnostic includes ID")


func _test_dispose_preempts_pending_and_ignores_late_completion() -> void:
	var scheduler := QueueScheduler.new()
	var bridge := ControllableBridge.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var initialize_results: Array = []
	var dispose_results: Array = []
	web_view.initialize(WebViewOptionsType.new()).connect(
		func(result): initialize_results.append(result)
	)
	web_view.dispose().connect(func(result): dispose_results.append(result))
	scheduler.pump()

	_expect_equal(initialize_results.size(), 1, "dispose resolves retired operation once")
	_expect_equal(
		initialize_results[0].code,
		WebViewResultType.ErrorCode.DISPOSED,
		"retired operation maps to disposed"
	)
	bridge.complete_operation(1, WebViewResultType.ErrorCode.OK)
	scheduler.pump()
	_expect_equal(dispose_results.size(), 0, "late retired completion is ignored")
	bridge.complete_operation(2, WebViewResultType.ErrorCode.OK)
	bridge.complete_operation(2, WebViewResultType.ErrorCode.BACKEND_FAILURE)
	scheduler.pump()
	_expect_equal(dispose_results.size(), 1, "dispose resolves exactly once")
	_expect(dispose_results[0].is_success, "dispose completion is preserved")


func _test_diagnostic_detail_is_safe_and_bounded() -> void:
	var scheduler := QueueScheduler.new()
	var bridge := ControllableBridge.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var results: Array = []
	web_view.initialize(WebViewOptionsType.new()).connect(func(result): results.append(result))
	bridge.complete_operation(
		1,
		WebViewResultType.ErrorCode.BACKEND_FAILURE,
		"stage https://example.com/path?secret=yes C:\\Users\\Ted\\secret 0x1234 " + "界".repeat(600)
	)
	scheduler.pump()

	var detail: String = results[0].diagnostic_detail
	_expect(not "example.com" in detail, "diagnostic redacts complete URLs")
	_expect(not "C:\\Users" in detail, "diagnostic redacts filesystem paths")
	_expect(not "0x1234" in detail, "diagnostic redacts memory addresses")
	_expect(detail.to_utf8_buffer().size() <= 1024, "diagnostic is bounded to 1024 UTF-8 bytes")


func _test_worker_completion_is_delivered_on_main_thread() -> void:
	var scheduler := QueueScheduler.new()
	var bridge := ControllableBridge.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var results: Array = []
	web_view.initialize(WebViewOptionsType.new()).connect(
		func(result):
			results.append(result)
			_expect(Thread.is_main_thread(), "result callback executes on Godot main thread")
	)
	var worker := Thread.new()
	_expect_equal(
		worker.start(func(): bridge.complete_operation(1, WebViewResultType.ErrorCode.OK)),
		OK,
		"worker starts"
	)
	worker.wait_to_finish()
	_expect_equal(results.size(), 0, "worker completion is not delivered inline")
	scheduler.pump()
	_expect_equal(results.size(), 1, "worker completion is delivered after main-thread pump")
	_expect(scheduler.last_delivery_was_main_thread, "scheduler delivery records main thread")


func _test_worker_completion_before_bridge_returns_resolves_once() -> void:
	var scheduler := QueueScheduler.new()
	var web_view = WebViewType._create_for_testing(
		EagerWorkerBridge.new(),
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	var results: Array = []
	web_view.initialize(WebViewOptionsType.new()).connect(func(result): results.append(result))
	scheduler.pump()
	_expect_equal(results.size(), 1, "eager worker completion resolves exactly once")
	_expect(results[0].is_success, "eager worker result is preserved")


func _test_host_locator_is_non_owning_and_resolved_per_operation() -> void:
	var host := RefCounted.new()
	var weak_host: WeakRef = weakref(host)
	var locator := CountingHostLocator.new(host)
	var bridge := ControllableBridge.new(locator)
	var scheduler := QueueScheduler.new()
	var web_view = WebViewType._create_for_testing(
		bridge,
		scheduler,
		FixedViewport.new(Vector2(200, 100))
	)
	web_view.initialize(WebViewOptionsType.new())
	web_view.open("https://example.test")
	web_view.close()
	web_view.dispose()
	_expect_equal(locator.count, 4, "Host Locator resolves for every operation")
	host = null
	_expect(weak_host.get_ref() == null, "Adapter/locator seam does not own located hosts")


func _test_unsupported_environment_is_deterministic() -> void:
	var scheduler := QueueScheduler.new()
	var web_view = WebViewType._create_for_testing(
		null,
		scheduler,
		FixedViewport.new(Vector2(200, 100)),
		false
	)
	var results: Array = []
	web_view.initialize(WebViewOptionsType.new()).connect(func(result): results.append(result))
	web_view.initialize(WebViewOptionsType.new()).connect(func(result): results.append(result))
	scheduler.pump()
	_expect_equal(results.size(), 2, "unsupported initialize calls resolve")
	_expect_equal(
		results[0].code,
		WebViewResultType.ErrorCode.UNSUPPORTED_ENVIRONMENT,
		"unsupported environment code"
	)
	_expect_equal(results[0].code, results[1].code, "unsupported code is deterministic")
	_expect_equal(
		results[0].diagnostic_detail,
		results[1].diagnostic_detail,
		"unsupported diagnostic is deterministic"
	)


func _expect(condition: bool, message: String) -> void:
	if not condition:
		_failures.append(message)


func _expect_equal(actual: Variant, expected: Variant, message: String) -> void:
	if actual != expected:
		_failures.append("%s: expected %s, got %s" % [message, expected, actual])


func _expect_approx(actual: float, expected: float, message: String) -> void:
	if not is_equal_approx(actual, expected):
		_failures.append("%s: expected %s, got %s" % [message, expected, actual])
