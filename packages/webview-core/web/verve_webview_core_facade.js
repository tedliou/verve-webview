(function (global) {
  "use strict";

  var phase = "uninitialized";
  var loadPromise = null;
  var backendCommandSink = null;
  var eventSinks = Object.create(null);
  var pending = Object.create(null);
  var activeOperations = Object.create(null);

  function sanitizeDiagnostic(value) {
    if (value === null || value === undefined || value === "") return null;
    var safe = String(value)
      .replace(/https?:\/\/[^\s"'<>]+/g, "[url]")
      .replace(/(?:[A-Za-z]:\\Users\\|\/(?:home|Users)\/)[^\s"'<>]+/g, "[user-path]");
    var encoded = new TextEncoder().encode(safe);
    if (encoded.length <= 1024) return safe;
    return new TextDecoder("utf-8", { fatal: false }).decode(encoded.slice(0, 1024))
      .replace(/\uFFFD$/, "");
  }

  function result(code, diagnosticDetail) {
    return Object.freeze({
      code: code,
      diagnosticDetail: sanitizeDiagnostic(diagnosticDetail),
      isSuccess: code === 0,
    });
  }

  function bindings() {
    if (typeof wasm_bindgen !== "function") {
      throw new TypeError("wasm-bindgen no-modules loader is missing");
    }
    return wasm_bindgen;
  }

  function load(wasmUrl) {
    if (phase === "ready") return Promise.resolve(result(0));
    if (loadPromise !== null) return loadPromise;
    phase = "loading";
    loadPromise = Promise.resolve().then(function () {
      return bindings()(wasmUrl);
    }).then(function () {
      phase = "ready";
      return result(0);
    }).catch(function (error) {
      phase = "failed";
      return result(400, String(error));
    });
    return loadPromise;
  }

  function createInstance(eventSink) {
    if (phase !== "ready") {
      return Object.freeze({ handle: 0, result: result(400, "Core is not loaded") });
    }
    try {
      var handle = bindings().browser_create_instance();
      if (typeof eventSink === "function") eventSinks[handle] = eventSink;
      return Object.freeze({ handle: handle, result: result(0) });
    } catch (error) {
      phase = "failed";
      return Object.freeze({ handle: 0, result: result(500, String(error)) });
    }
  }

  function copy(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function retireActive(instance) {
    var operation = activeOperations[instance];
    if (!operation || !pending[operation]) return;
    pending[operation].resolve(result(203, "Operation retired by dispose"));
    delete pending[operation];
    delete activeOperations[instance];
  }

  function completeBackend(request, backendResult) {
    var code = backendResult && Number.isInteger(backendResult.code)
      ? backendResult.code
      : 302;
    var detail = backendResult && typeof backendResult.diagnosticDetail === "string"
      ? sanitizeDiagnostic(backendResult.diagnosticDetail) || ""
      : "";
    var completion = JSON.parse(bindings().browser_complete(
      request.instance,
      request.operation,
      code,
      detail
    ));
    if (completion.event === null) return;

    var event = copy(completion.event);
    var entry = pending[event.operation];
    if (entry) {
      entry.resolve(Object.freeze(event.result));
      delete pending[event.operation];
    }
    if (activeOperations[event.instance] === event.operation) {
      delete activeOperations[event.instance];
    }
    var sink = eventSinks[event.instance];
    if (typeof sink === "function") sink(Object.freeze(event));
    if (event.kind === "dispose") delete eventSinks[event.instance];
  }

  function dispatch(request) {
    Promise.resolve().then(function () {
      if (typeof backendCommandSink !== "function") {
        return { code: 302, diagnosticDetail: "Backend command sink is not registered" };
      }
      return backendCommandSink(Object.freeze(copy(request)));
    }).catch(function (error) {
      return { code: 302, diagnosticDetail: String(error) };
    }).then(function (backendResult) {
      try {
        completeBackend(request, backendResult);
      } catch (error) {
        phase = "failed";
        var entry = pending[request.operation];
        if (entry) {
          entry.resolve(result(500, String(error)));
          delete pending[request.operation];
        }
        delete activeOperations[request.instance];
      }
    });
  }

  function start(instance, kind, invoke) {
    if (phase !== "ready") return Promise.resolve(result(400, "Core is not loaded"));
    var envelope;
    try {
      envelope = JSON.parse(invoke());
    } catch (error) {
      phase = "failed";
      return Promise.resolve(result(500, String(error)));
    }
    if (envelope.request === null) {
      return Promise.resolve(Object.freeze(envelope.result));
    }
    if (kind === "dispose") retireActive(instance);
    return new Promise(function (resolve) {
      pending[envelope.request.operation] = { resolve: resolve };
      activeOperations[instance] = envelope.request.operation;
      dispatch(envelope.request);
    });
  }

  global.VerveWebViewCore = Object.freeze({
    load: load,
    createInstance: createInstance,
    setBackendCommandSink: function (callback) {
      backendCommandSink = typeof callback === "function" ? callback : null;
    },
    initialize: function (instance, optionsJson) {
      var copied = String(optionsJson);
      return start(instance, "initialize", function () {
        return bindings().browser_initialize(instance, copied);
      });
    },
    open: function (instance, url, geometry) {
      var copiedUrl = String(url);
      var copiedGeometry = geometry === null || geometry === undefined
        ? null
        : {
            x: Number(geometry.x),
            y: Number(geometry.y),
            width: Number(geometry.width),
            height: Number(geometry.height),
          };
      return start(instance, "open", function () {
        return bindings().browser_open(
          instance,
          copiedUrl,
          copiedGeometry !== null,
          copiedGeometry === null ? 0 : copiedGeometry.x,
          copiedGeometry === null ? 0 : copiedGeometry.y,
          copiedGeometry === null ? 0 : copiedGeometry.width,
          copiedGeometry === null ? 0 : copiedGeometry.height
        );
      });
    },
    close: function (instance) {
      return start(instance, "close", function () {
        return bindings().browser_close(instance);
      });
    },
    dispose: function (instance) {
      return start(instance, "dispose", function () {
        return bindings().browser_dispose(instance);
      });
    },
  });
})(window);
