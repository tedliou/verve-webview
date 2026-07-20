// PROTOTYPE ONLY: thin Unity WebGL transport; Core state stays in Rust.
mergeInto(LibraryManager.library, {
  VerveWebView_Initialize: function (requestId, wasmUrlPtr, callback) {
    var wasmUrl = UTF8ToString(wasmUrlPtr);
    VerveWebViewCore.ready(wasmUrl).then(function (json) {
      var ptr = stringToNewUTF8(json);
      {{{ makeDynCall('vii', 'callback') }}}(requestId, ptr);
    }).catch(function (error) {
      var ptr = stringToNewUTF8(String(error));
      {{{ makeDynCall('vii', 'callback') }}}(requestId, ptr);
    });
  },

  VerveWebView_SetEventSink: function (callback) {
    VerveWebViewCore.setEventSink(function (json) {
      var ptr = stringToNewUTF8(json);
      {{{ makeDynCall('vii', 'callback') }}}(0, ptr);
    });
  },

  VerveWebView_CreateInstance: function () {
    return stringToNewUTF8(VerveWebViewCore.createInstance());
  },

  VerveWebView_Request: function (operationPtr, handle, payloadPtr) {
    return stringToNewUTF8(VerveWebViewCore.request(
      UTF8ToString(operationPtr),
      handle,
      UTF8ToString(payloadPtr)
    ));
  },

  VerveWebView_PrototypeTrap: function () {
    return stringToNewUTF8(VerveWebViewCore.prototypeTrap());
  },

  VerveWebView_PrototypePublish: function (jsonPtr) {
    var json = UTF8ToString(jsonPtr);
    document.documentElement.setAttribute('data-verve-prototype-result', json);
    var output = document.getElementById('verve-prototype-result');
    if (!output) {
      output = document.createElement('pre');
      output.id = 'verve-prototype-result';
      document.body.appendChild(output);
    }
    output.textContent = json;
  },

  VerveWebView_Free: function (value) {
    _free(value);
  }
});
