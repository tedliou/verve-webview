(async function () {
  "use strict";
  var trapped = false;
  var error = "";
  try {
    await wasm_bindgen("verve_webview_core_test_bg.wasm");
    wasm_bindgen.browser_test_trap();
  } catch (caught) {
    trapped = true;
    error = String(caught);
  }
  window.parent.postMessage({ trapped: trapped, error: error }, "*");
})();
