(async function () {
  "use strict";

  var assertions = 0;

  function assert(condition, message) {
    assertions += 1;
    if (!condition) throw new Error(message);
  }

  function waitForBackend(queue) {
    return new Promise(function (resolve, reject) {
      var attempts = 0;
      function poll() {
        if (queue.length > 0) return resolve(queue.shift());
        attempts += 1;
        if (attempts > 100) return reject(new Error("backend request did not arrive"));
        setTimeout(poll, 0);
      }
      poll();
    });
  }

  async function finish(queue, promise, code, diagnosticDetail) {
    var completion = await waitForBackend(queue);
    completion.resolve({ code: code, diagnosticDetail: diagnosticDetail || null });
    return promise;
  }

  function invokeOperation(operation, instance) {
    if (operation === "initialize") {
      return window.VerveWebViewCore.initialize(instance, "{}");
    }
    if (operation === "open") {
      return window.VerveWebViewCore.open(instance, "https://example.com/vector");
    }
    if (operation === "close") {
      return window.VerveWebViewCore.close(instance);
    }
    return window.VerveWebViewCore.dispose(instance);
  }

  async function acceptedOperation(backend, operation, instance, code) {
    var promise = invokeOperation(operation, instance);
    var completion = await waitForBackend(backend);
    completion.resolve({ code: code });
    return promise;
  }

  async function prepareState(backend, state) {
    var instance = window.VerveWebViewCore.createInstance().handle;
    var pendingDispose = null;
    if (state !== "uninitialized") {
      var initializeCode = state === "invalidated" ? 500 : 0;
      await acceptedOperation(backend, "initialize", instance, initializeCode);
    }
    if (state === "surface_open") {
      await acceptedOperation(backend, "open", instance, 0);
    } else if (state === "disposing" || state === "disposed") {
      var disposePromise = window.VerveWebViewCore.dispose(instance);
      var disposeBackend = await waitForBackend(backend);
      if (state === "disposing") {
        pendingDispose = { promise: disposePromise, backend: disposeBackend };
      } else {
        disposeBackend.resolve({ code: 0 });
        await disposePromise;
      }
    }
    return { instance: instance, pendingDispose: pendingDispose };
  }

  async function cleanupState(backend, prepared) {
    if (prepared.pendingDispose !== null) {
      prepared.pendingDispose.backend.resolve({ code: 0 });
      await prepared.pendingDispose.promise;
      return;
    }
    var dispose = window.VerveWebViewCore.dispose(prepared.instance);
    await new Promise(function (resolve) { setTimeout(resolve, 0); });
    if (backend.length > 0) {
      backend.shift().resolve({ code: 0 });
    }
    await dispose;
  }

  async function runLifecycleVectors(contract, backend) {
    var count = 0;
    for (var operationIndex = 0; operationIndex < contract.operations.length; operationIndex += 1) {
      var operation = contract.operations[operationIndex];
      for (var stateIndex = 0; stateIndex < contract.lifecycle.states.length; stateIndex += 1) {
        var state = contract.lifecycle.states[stateIndex];
        var prepared = await prepareState(backend, state);
        var promise = invokeOperation(operation.name, prepared.instance);
        await new Promise(function (resolve) { setTimeout(resolve, 0); });
        var accepted = backend.length > 0;
        var expected = operation.legal_pre_states.indexOf(state) !== -1;
        assert(
          accepted === expected,
          "lifecycle vector mismatch: " + operation.name + " from " + state
        );
        if (accepted) backend.shift().resolve({ code: 0 });
        await promise;
        await cleanupState(backend, prepared);
        count += 1;
      }
    }
    return count;
  }

  async function runErrorVectors(contract, backend) {
    for (var index = 0; index < contract.public_error_codes.length; index += 1) {
      var vector = contract.public_error_codes[index];
      var instance = window.VerveWebViewCore.createInstance().handle;
      var outcome = await acceptedOperation(backend, "initialize", instance, vector.id);
      assert(outcome.code === vector.id, "error wire vector mismatch: " + vector.name);
      await cleanupState(backend, { instance: instance, pendingDispose: null });
    }
    return contract.public_error_codes.length;
  }

  function loadFailure(wasm) {
    return new Promise(function (resolve, reject) {
      var iframe = document.createElement("iframe");
      var timer = setTimeout(function () {
        reject(new Error("load failure scenario timed out: " + wasm));
      }, 5000);
      function receive(event) {
        if (event.source !== iframe.contentWindow) return;
        clearTimeout(timer);
        window.removeEventListener("message", receive);
        iframe.remove();
        resolve(event.data);
      }
      window.addEventListener("message", receive);
      iframe.src = "load_failure_harness.html?wasm=" + encodeURIComponent(wasm);
      document.body.appendChild(iframe);
    });
  }

  function observeTrap() {
    return new Promise(function (resolve, reject) {
      var iframe = document.createElement("iframe");
      var timer = setTimeout(function () {
        reject(new Error("Rust trap scenario timed out"));
      }, 5000);
      function receive(event) {
        if (event.source !== iframe.contentWindow) return;
        clearTimeout(timer);
        window.removeEventListener("message", receive);
        iframe.remove();
        resolve(event.data);
      }
      window.addEventListener("message", receive);
      iframe.src = "trap_harness.html";
      document.body.appendChild(iframe);
    });
  }

  try {
    var contract = await (await fetch("api-contract.json")).json();
    assert(
      JSON.stringify(contract.operations.map(function (operation) { return operation.name; }))
        === JSON.stringify(["initialize", "open", "close", "dispose"]),
      "browser harness consumes the shared generated operation vectors"
    );
    assert(contract.public_error_codes.length === 20, "browser harness consumes all error vectors");

    var loaded = await window.VerveWebViewCore.load("verve_webview_core_bg.wasm");
    assert(loaded.code === 0, "browser Core loads");

    var events = [];
    var created = window.VerveWebViewCore.createInstance(function (event) {
      events.push(event);
    });
    assert(created.result.code === 0, "SDK Instance is created");
    assert(
      Number.isInteger(created.handle) && created.handle > 0 && created.handle <= 0xffffffff,
      "instance handle is opaque u32"
    );

    var backend = [];
    window.VerveWebViewCore.setBackendCommandSink(function (request) {
      return new Promise(function (resolve) {
        backend.push({ request: request, resolve: resolve });
      });
    });
    var lifecycleVectorCount = await runLifecycleVectors(contract, backend);
    var errorVectorCount = await runErrorVectors(contract, backend);

    assert((await window.VerveWebViewCore.open(created.handle, "https://example.com")).code === 200,
      "open before initialize follows generated not_initialized vector");
    assert((await window.VerveWebViewCore.initialize(created.handle, "x".repeat(4097))).code === 100,
      "bounded initialization payload follows invalid_options vector");

    var initializing = window.VerveWebViewCore.initialize(created.handle, "{\"copy\":true}");
    assert((await window.VerveWebViewCore.close(created.handle)).code === 202,
      "strict single-flight follows operation_in_progress vector");
    var initBackend = await waitForBackend(backend);
    assert(initBackend.request.payload === "{\"copy\":true}", "options payload is copied");
    assert(
      Number.isInteger(initBackend.request.operation)
        && initBackend.request.operation > 0
        && initBackend.request.operation <= 0xffffffff,
      "operation handle is opaque u32"
    );
    initBackend.resolve({ code: 0 });
    assert((await initializing).code === 0, "initialize Promise completes");
    assert((await window.VerveWebViewCore.initialize(created.handle, "{}")).code === 201,
      "repeat initialize follows already_initialized vector");
    assert((await window.VerveWebViewCore.close(created.handle)).code === 204,
      "close without Surface follows surface_not_open vector");
    assert((await window.VerveWebViewCore.open(created.handle, "file:///etc/passwd")).code === 101,
      "URL validation follows invalid_url vector");
    assert((await window.VerveWebViewCore.open(created.handle, "https://example.com", {
      x: 0, y: 0, width: 0, height: 1,
    })).code === 102, "geometry validation follows invalid_geometry vector");

    var geometry = { x: 0.1, y: 0.2, width: 0.5, height: 0.6 };
    var opening = window.VerveWebViewCore.open(
      created.handle,
      "https://example.com/path",
      geometry
    );
    geometry.width = 0;
    var openBackend = await waitForBackend(backend);
    assert(openBackend.request.geometry.width === 0.5, "geometry payload is copied");
    openBackend.resolve({ code: 0 });
    assert((await opening).code === 0, "open Promise completes");

    var second = window.VerveWebViewCore.createInstance(function () {});
    assert(second.handle !== created.handle, "instance handles are unique");
    assert((await finish(
      backend,
      window.VerveWebViewCore.initialize(second.handle, "{}"),
      0
    )).code === 0, "second SDK Instance initializes");
    assert((await window.VerveWebViewCore.open(second.handle, "https://example.com")).code === 205,
      "Surface Lease follows surface_in_use vector");

    var unknown = window.VerveWebViewCore.close(created.handle);
    assert((await finish(backend, unknown, 999999)).code === 401,
      "unknown wire ID follows abi_mismatch vector");
    var longDiagnostic = "https://secret.example/path?token=value /home/user/private " + "é".repeat(800);
    var failedClose = window.VerveWebViewCore.close(created.handle);
    var failedResult = await finish(backend, failedClose, 302, longDiagnostic);
    assert(failedResult.code === 302, "backend failure is explicit");
    assert(
      new TextEncoder().encode(failedResult.diagnosticDetail).length <= 1024,
      "diagnostic detail is bounded at a UTF-8 boundary"
    );
    assert(
      failedResult.diagnosticDetail.indexOf("secret.example") === -1
        && failedResult.diagnosticDetail.indexOf("/home/user/private") === -1,
      "diagnostic detail removes URLs and user filesystem paths"
    );

    var navigating = window.VerveWebViewCore.open(created.handle, "https://example.com/late");
    var lateBackend = await waitForBackend(backend);
    var disposing = window.VerveWebViewCore.dispose(created.handle);
    assert((await navigating).code === 203, "dispose settles the retired Promise");
    var disposeBackend = await waitForBackend(backend);
    var eventCountBeforeLate = events.length;
    lateBackend.resolve({ code: 0 });
    await Promise.resolve();
    await new Promise(function (resolve) { setTimeout(resolve, 0); });
    assert(events.length === eventCountBeforeLate, "late completion is diagnostic-only");
    disposeBackend.resolve({ code: 0 });
    assert((await disposing).code === 0, "dispose Promise completes");
    var eventCountAfterDispose = events.length;
    assert((await window.VerveWebViewCore.open(created.handle, "https://example.com")).code === 203,
      "disposed instance is terminal");
    assert(events.length === eventCountAfterDispose, "disposed callback is released");

    var missing = await loadFailure("missing.wasm");
    assert(missing.code === 400, "missing Wasm returns core_load_failed");
    var corrupt = await loadFailure("corrupt.wasm");
    assert(corrupt.code === 400, "corrupt Wasm returns core_load_failed");
    var trap = await observeTrap();
    assert(trap.trapped === true, "Rust panic aborts as a WebAssembly trap");
    assert(trap.error.indexOf("RuntimeError") !== -1, "trap is explicit to JavaScript");

    document.querySelector("#result").textContent = JSON.stringify({
      status: "passed",
      assertions: assertions,
      lifecycleVectors: lifecycleVectorCount,
      errorVectors: errorVectorCount,
      completionEvents: events.length,
    });
  } catch (error) {
    document.querySelector("#result").textContent = JSON.stringify({
      status: "failed",
      assertions: assertions,
      error: String(error && error.stack || error),
    });
  }
})();
