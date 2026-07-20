(function (global) {
  "use strict";

  // PROTOTYPE ONLY: stable engine-neutral facade over wasm-bindgen no-modules.
  var phase = "uninitialized";
  var sink = null;
  var liveGeneration = Object.create(null);
  var disposed = Object.create(null);

  function bindings() {
    // wasm-bindgen no-modules emits a global lexical binding (`let`), not a
    // property on window. Resolve the configured name and retain compatibility
    // with the default name so a stale staged bundle fails visibly in CI.
    if (typeof verve_webview_core_bindgen === "function") {
      return verve_webview_core_bindgen;
    }
    if (typeof wasm_bindgen === "function") return wasm_bindgen;
    throw new TypeError("wasm-bindgen no-modules loader is missing");
  }

  function envelope(ok, code, detail) {
    return JSON.stringify({ ok: ok, code: code, detail: detail || null });
  }

  function emit(event) {
    if (typeof sink === "function") sink(JSON.stringify(event));
  }

  async function ready(wasmUrl) {
    if (phase === "ready") return envelope(true, "ready");
    if (phase === "loading") return envelope(false, "initialization_pending");
    phase = "loading";
    try {
      await bindings()(wasmUrl);
      phase = "ready";
      return envelope(true, "ready");
    } catch (error) {
      phase = "failed";
      emit({ kind: "initialization_failed", message: String(error) });
      throw new Error(envelope(false, "core_load_failed", String(error)));
    }
  }

  function createInstance() {
    if (phase !== "ready") return envelope(false, "not_initialized");
    var handle = bindings().create_instance();
    liveGeneration[handle] = 0;
    disposed[handle] = false;
    return JSON.stringify({ ok: true, code: "created", handle: handle });
  }

  function request(operation, handle, payloadJson) {
    if (phase !== "ready") return envelope(false, "not_initialized");
    var generation = (liveGeneration[handle] || 0) + 1;
    liveGeneration[handle] = generation;
    var response = bindings().request(
      handle,
      operation,
      generation
    );
    var parsed = JSON.parse(response);
    if (operation === "dispose" && parsed.ok) disposed[handle] = true;

    // Deliberately asynchronous: this is the late-completion behavior the
    // engine adapters must observe. A stale or disposed generation is dropped.
    Promise.resolve().then(function () {
      if (disposed[handle] || liveGeneration[handle] !== generation) return;
      emit({
        kind: "operation_completed",
        operation: operation,
        handle: handle,
        generation: generation,
        payload: payloadJson || null,
        result: parsed,
      });
    });
    return response;
  }

  function trap() {
    try {
      bindings().prototype_trap();
      return envelope(false, "trap_not_observed");
    } catch (error) {
      phase = "failed";
      emit({ kind: "core_trapped", message: String(error) });
      return envelope(false, "core_trapped", String(error));
    }
  }

  global.VerveWebViewCore = Object.freeze({
    ready: ready,
    createInstance: createInstance,
    request: request,
    setEventSink: function (callback) { sink = callback; },
    prototypeTrap: trap,
    prototypePhase: function () { return phase; },
  });
})(window);
