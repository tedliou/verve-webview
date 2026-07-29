(async function () {
  "use strict";

  var assertions = 0;

  function assert(condition, message) {
    assertions += 1;
    if (!condition) throw new Error(message);
  }

  function approximately(actual, expected, message) {
    assert(Math.abs(actual - expected) <= 1, message + ": " + actual);
  }

  function delay(milliseconds) {
    return new Promise(function (resolve) { setTimeout(resolve, milliseconds); });
  }

  function hostElement() {
    var host = document.createElement("div");
    host.id = "game-host";
    host.style.position = "absolute";
    host.style.left = "40px";
    host.style.top = "30px";
    host.style.width = "400px";
    host.style.height = "240px";
    document.body.appendChild(host);
    return host;
  }

  try {
    var loadResult = await window.VerveWebViewCore.load("verve_webview_core_bg.wasm");
    assert(loadResult.isSuccess, "Core must load");

    var host = document.getElementById("game-host");
    var backend = window.VerveWebViewWebBackend.install({
      core: window.VerveWebViewCore,
      locateHost: function () { return host; },
    });
    assert(backend !== null, "Backend install must return a controller");

    var instance = window.VerveWebViewCore.createInstance().handle;
    var initializeSettled = false;
    var initializePromise = window.VerveWebViewCore.initialize(instance, "{}")
      .then(function (value) {
        initializeSettled = true;
        return value;
      });
    assert(!initializeSettled, "accepted initialize must not complete inline");
    assert((await initializePromise).isSuccess, "initialize must succeed");

    var rejectedScheme = await window.VerveWebViewCore.open(
      instance,
      "javascript:document.body.textContent='owned'"
    );
    assert(rejectedScheme.code === 101, "disallowed direct schemes must fail invalid_url");
    assert(
      host.querySelectorAll("iframe[data-verve-webview-surface]").length === 0,
      "a disallowed scheme must not create a Surface"
    );

    var openResult = await window.VerveWebViewCore.open(
      instance,
      new URL("surface_content.html", window.location.href).href,
      { x: 0.25, y: 0.125, width: 0.5, height: 0.75 }
    );
    assert(openResult.isSuccess, "open must succeed");

    var frames = host.querySelectorAll("iframe[data-verve-webview-surface]");
    assert(frames.length === 1, "open must create exactly one WebView Surface");
    var frame = frames[0];
    assert(
      frame.getAttribute("sandbox") === "allow-scripts allow-forms",
      "Surface sandbox must allow only scripts and forms"
    );
    assert(
      frame.getAttribute("allow").indexOf("'none'") !== -1,
      "device permissions must be denied"
    );

    var rectangle = frame.getBoundingClientRect();
    approximately(rectangle.left, 140, "normalized x must use the complete host");
    approximately(rectangle.top, 60, "normalized y must use the complete host");
    approximately(rectangle.width, 200, "normalized width must use the complete host");
    approximately(rectangle.height, 180, "normalized height must use the complete host");
    assert(document.activeElement === frame, "the opened Surface must receive focus");
    await delay(50);
    assert(frame.contentDocument === null, "Surface content must have an opaque origin");
    var opaqueLocation = false;
    try {
      void frame.contentWindow.location.href;
    } catch (error) {
      opaqueLocation = error && error.name === "SecurityError";
    }
    assert(opaqueLocation, "opaque Surface location must not be readable by the exported app");
    assert(
      !frame.sandbox.contains("allow-popups") &&
      !frame.sandbox.contains("allow-popups-to-escape-sandbox"),
      "new browsing context capabilities must be omitted"
    );
    assert(
      !frame.sandbox.contains("allow-top-navigation") &&
      !frame.sandbox.contains("allow-top-navigation-by-user-activation"),
      "top-level navigation capabilities must be omitted"
    );
    var framePolicy = frame.permissionsPolicy || frame.featurePolicy;
    assert(
      framePolicy && !framePolicy.allowsFeature("geolocation"),
      "device permissions must be denied"
    );
    assert(
      window.location.pathname.endsWith("/browser_backend_harness.html"),
      "Surface content must not navigate the exported app"
    );

    host.style.width = "600px";
    host.style.height = "320px";
    window.dispatchEvent(new Event("resize"));
    await delay(50);
    rectangle = frame.getBoundingClientRect();
    approximately(rectangle.left, 190, "resize must reapply normalized x");
    approximately(rectangle.top, 70, "resize must reapply normalized y");
    approximately(rectangle.width, 300, "resize must reapply normalized width");
    approximately(rectangle.height, 240, "resize must reapply normalized height");

    var secondOpen = await window.VerveWebViewCore.open(
      instance,
      new URL("surface_content.html?second", window.location.href).href,
      { x: 0, y: 0, width: 1, height: 1 }
    );
    assert(secondOpen.isSuccess, "renavigation must succeed");
    assert(
      host.querySelectorAll("iframe[data-verve-webview-surface]").length === 1,
      "renavigation must reuse the only Surface"
    );

    host.remove();
    await delay(50);
    assert(!frame.isConnected, "host loss must remove the Surface");
    var closeAfterHostLoss = await window.VerveWebViewCore.close(instance);
    assert(
      closeAfterHostLoss.code === 204,
      "host loss must return Core to initialized/closed"
    );
    host = hostElement();
    assert(
      (await window.VerveWebViewCore.open(
        instance,
        new URL("surface_content.html?recovered", window.location.href).href
      )).isSuccess,
      "a later open may recover on a newly resolved host"
    );
    assert((await window.VerveWebViewCore.close(instance)).isSuccess, "close must succeed");
    assert(
      host.querySelectorAll("iframe[data-verve-webview-surface]").length === 0,
      "close must remove the Surface"
    );
    assert((await window.VerveWebViewCore.dispose(instance)).isSuccess, "dispose must succeed");

    var owner = window.VerveWebViewCore.createInstance().handle;
    var competitor = window.VerveWebViewCore.createInstance().handle;
    assert(
      (await window.VerveWebViewCore.initialize(owner, "{}")).isSuccess,
      "lease owner must initialize"
    );
    assert(
      (await window.VerveWebViewCore.initialize(competitor, "{}")).isSuccess,
      "lease competitor must initialize"
    );
    assert(
      (await window.VerveWebViewCore.open(
        owner,
        new URL("surface_content.html?owner", window.location.href).href
      )).isSuccess,
      "lease owner must open"
    );
    var competingOpen = await window.VerveWebViewCore.open(
      competitor,
      new URL("surface_content.html?competitor", window.location.href).href
    );
    assert(competingOpen.code === 205, "a competing open must fail surface_in_use");
    assert(
      host.querySelectorAll("iframe[data-verve-webview-surface]").length === 1,
      "a competing open must never create a second Surface"
    );
    assert((await window.VerveWebViewCore.close(owner)).isSuccess, "owner close must succeed");
    assert(
      (await window.VerveWebViewCore.open(
        competitor,
        new URL("surface_content.html?competitor", window.location.href).href
      )).isSuccess,
      "released Surface Lease must be reusable"
    );
    assert((await window.VerveWebViewCore.close(competitor)).isSuccess, "competitor close must succeed");
    assert((await window.VerveWebViewCore.dispose(owner)).isSuccess, "owner dispose must succeed");
    assert((await window.VerveWebViewCore.dispose(competitor)).isSuccess, "competitor dispose must succeed");
    backend.uninstall();

    var unavailableBackend = window.VerveWebViewWebBackend.install({
      core: window.VerveWebViewCore,
      locateHost: function () { return null; },
    });
    var unavailable = window.VerveWebViewCore.createInstance().handle;
    var unavailableResult = await window.VerveWebViewCore.initialize(unavailable, "{}");
    assert(unavailableResult.code === 300, "missing DOM host must fail host_unavailable");
    assert((await window.VerveWebViewCore.dispose(unavailable)).isSuccess, "failed instance must dispose");
    unavailableBackend.uninstall();

    var delayedHost = host;
    var delayOpen = false;
    var releaseLocator = null;
    var staleBackend = window.VerveWebViewWebBackend.install({
      core: window.VerveWebViewCore,
      locateHost: function () {
        if (!delayOpen) return delayedHost;
        return new Promise(function (resolve) { releaseLocator = resolve; });
      },
    });
    var stale = window.VerveWebViewCore.createInstance().handle;
    assert(
      (await window.VerveWebViewCore.initialize(stale, "{}")).isSuccess,
      "stale test instance must initialize"
    );
    delayOpen = true;
    var staleOpen = window.VerveWebViewCore.open(
      stale,
      new URL("surface_content.html?stale", window.location.href).href
    );
    await delay(20);
    var staleDispose = window.VerveWebViewCore.dispose(stale);
    await delay(20);
    releaseLocator(delayedHost);
    var staleOpenResult = await staleOpen;
    assert(staleOpenResult.code === 203, "dispose must retire the pending open");
    assert((await staleDispose).isSuccess, "dispose cleanup must complete");
    assert(
      delayedHost.querySelectorAll("iframe[data-verve-webview-surface]").length === 0,
      "stale open must never attach a Surface"
    );
    staleBackend.uninstall();

    document.getElementById("result").textContent = JSON.stringify({
      status: "passed",
      assertions: assertions,
      slices: [
        "sandboxed_surface",
        "browser_security",
        "resize",
        "host_loss",
        "surface_lease",
        "host_unavailable",
        "stale_completion",
      ],
    });
  } catch (error) {
    document.getElementById("result").textContent = JSON.stringify({
      status: "failed",
      assertions: assertions,
      message: String(error && error.stack || error),
    });
  }
})();
