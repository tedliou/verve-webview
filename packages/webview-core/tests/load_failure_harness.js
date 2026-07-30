(async function () {
  "use strict";
  var wasm = new URLSearchParams(window.location.search).get("wasm");
  var outcome = await window.VerveWebViewCore.load(wasm);
  window.parent.postMessage({
    code: outcome.code,
    diagnosticDetail: outcome.diagnosticDetail,
  }, "*");
})();
