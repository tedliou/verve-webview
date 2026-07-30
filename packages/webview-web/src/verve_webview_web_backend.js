(function (global) {
  "use strict";

  var installedController = null;
  var surfaceLease = null;

  function result(code, diagnosticDetail) {
    return {
      code: code,
      diagnosticDetail: diagnosticDetail || null,
    };
  }

  function copyGeometry(value) {
    if (value === null || value === undefined) {
      return { x: 0, y: 0, width: 1, height: 1 };
    }
    return {
      x: Number(value.x),
      y: Number(value.y),
      width: Number(value.width),
      height: Number(value.height),
    };
  }

  function validUrl(value) {
    try {
      var parsed = new URL(String(value));
      return (parsed.protocol === "http:" || parsed.protocol === "https:") &&
        parsed.hostname !== "" &&
        parsed.username === "" &&
        parsed.password === "";
    } catch (_error) {
      return false;
    }
  }

  function install(options) {
    if (installedController !== null) {
      throw new Error("Web Platform Backend is already installed");
    }
    if (!options || !options.core ||
        typeof options.core.setBackendCommandSink !== "function") {
      throw new TypeError("A loaded VerveWebViewCore facade is required");
    }
    if (typeof options.locateHost !== "function") {
      throw new TypeError("A Host Locator function is required");
    }

    var core = options.core;
    var locateHost = options.locateHost;
    var generations = Object.create(null);
    var surfaces = Object.create(null);
    var serial = Promise.resolve();
    var removed = false;

    function rememberGeneration(request) {
      var current = generations[request.instance] || 0;
      if (request.generation > current) generations[request.instance] = request.generation;
    }

    function isCurrent(request) {
      return !removed && generations[request.instance] === request.generation;
    }

    function nextMainLoop(task) {
      return new Promise(function (resolve) {
        setTimeout(resolve, 0);
      }).then(task);
    }

    function resolveHost() {
      return Promise.resolve().then(locateHost).then(function (host) {
        if (!(host instanceof global.HTMLElement) || !host.isConnected) return null;
        return host;
      });
    }

    function applyGeometry(surface, host, geometry) {
      var hostRectangle = host.getBoundingClientRect();
      var frame = surface.frame;
      frame.style.left = hostRectangle.left + geometry.x * hostRectangle.width + "px";
      frame.style.top = hostRectangle.top + geometry.y * hostRectangle.height + "px";
      frame.style.width = geometry.width * hostRectangle.width + "px";
      frame.style.height = geometry.height * hostRectangle.height + "px";
    }

    function disconnectObservers(surface) {
      if (surface.resizeObserver !== null) surface.resizeObserver.disconnect();
      if (surface.mutationObserver !== null) surface.mutationObserver.disconnect();
      global.removeEventListener("resize", surface.refresh);
      global.removeEventListener("scroll", surface.refresh, true);
    }

    function removeSurface(instance) {
      var surface = surfaces[instance];
      if (!surface) return;
      disconnectObservers(surface);
      if (surface.frame.parentNode !== null) surface.frame.parentNode.removeChild(surface.frame);
      delete surfaces[instance];
      if (surfaceLease === Number(instance)) surfaceLease = null;
    }

    function reportHostLost(instance) {
      removeSurface(instance);
      if (typeof core.reportHostLost === "function") core.reportHostLost(instance);
    }

    function observeSurface(instance, surface) {
      var refreshPending = false;
      surface.refresh = function () {
        if (refreshPending || surfaces[instance] !== surface) return;
        refreshPending = true;
        var maintenance = serial.then(function () {
          return nextMainLoop(function () {
            refreshPending = false;
            return resolveHost().then(function (host) {
              if (surfaces[instance] !== surface) return;
              if (host === null || host !== surface.host || !surface.frame.isConnected) {
                reportHostLost(instance);
                return;
              }
              applyGeometry(surface, host, surface.geometry);
            });
          });
        });
        serial = maintenance.catch(function () {
          refreshPending = false;
        });
      };
      surface.resizeObserver = typeof global.ResizeObserver === "function"
        ? new global.ResizeObserver(surface.refresh)
        : null;
      if (surface.resizeObserver !== null) surface.resizeObserver.observe(surface.host);
      surface.mutationObserver = typeof global.MutationObserver === "function"
        ? new global.MutationObserver(surface.refresh)
        : null;
      if (surface.mutationObserver !== null) {
        surface.mutationObserver.observe(global.document, { childList: true, subtree: true });
      }
      global.addEventListener("resize", surface.refresh);
      global.addEventListener("scroll", surface.refresh, true);
    }

    function createSurface(instance, host, geometry) {
      var frame = global.document.createElement("iframe");
      frame.setAttribute("data-verve-webview-surface", "");
      frame.setAttribute("sandbox", "allow-scripts allow-forms");
      frame.setAttribute(
        "allow",
        "camera 'none'; microphone 'none'; geolocation 'none'; " +
        "clipboard-read 'none'; clipboard-write 'none'; display-capture 'none'; " +
        "fullscreen 'none'; payment 'none'; usb 'none'; serial 'none'; hid 'none'"
      );
      frame.setAttribute("referrerpolicy", "strict-origin-when-cross-origin");
      frame.style.position = "fixed";
      frame.style.display = "block";
      frame.style.border = "0";
      frame.style.margin = "0";
      frame.style.padding = "0";
      frame.style.zIndex = "2147483647";
      frame.style.background = "transparent";

      var surface = {
        frame: frame,
        geometry: geometry,
        host: host,
        mutationObserver: null,
        refresh: null,
        resizeObserver: null,
      };
      host.appendChild(frame);
      applyGeometry(surface, host, geometry);
      observeSurface(instance, surface);
      surfaces[instance] = surface;
      surfaceLease = instance;
      return surface;
    }

    function initialize(request) {
      return resolveHost().then(function (host) {
        if (!isCurrent(request)) return result(203, "stale initialize generation");
        return host === null
          ? result(300, "DOM host is unavailable")
          : result(0);
      });
    }

    function open(request) {
      if (!validUrl(request.payload)) return Promise.resolve(result(101, "URL policy rejected"));
      return resolveHost().then(function (host) {
        if (!isCurrent(request)) return result(203, "stale open generation");
        if (host === null) return result(300, "DOM host is unavailable");
        if (surfaceLease !== null && surfaceLease !== request.instance) return result(205);

        var geometry = copyGeometry(request.geometry);
        var surface = surfaces[request.instance];
        if (surface && (surface.host !== host || !surface.frame.isConnected)) {
          reportHostLost(request.instance);
          return result(301, "DOM host was lost");
        }
        if (!surface) surface = createSurface(request.instance, host, geometry);
        surface.geometry = geometry;
        applyGeometry(surface, host, geometry);
        if (!isCurrent(request)) {
          removeSurface(request.instance);
          return result(203, "stale open generation");
        }
        surface.frame.src = String(request.payload);
        surface.frame.focus({ preventScroll: true });
        return result(0);
      }).catch(function (error) {
        removeSurface(request.instance);
        return result(302, String(error));
      });
    }

    function close(request) {
      return resolveHost().then(function (host) {
        if (!isCurrent(request)) return result(203, "stale close generation");
        var surface = surfaces[request.instance];
        if (!surface || host === null || host !== surface.host || !surface.frame.isConnected) {
          removeSurface(request.instance);
          return result(301, "DOM host was lost");
        }
        removeSurface(request.instance);
        return result(0);
      });
    }

    function dispose(request) {
      removeSurface(request.instance);
      return Promise.resolve(result(0));
    }

    function execute(request) {
      if (request.kind === "initialize") return initialize(request);
      if (request.kind === "open") return open(request);
      if (request.kind === "close") return close(request);
      if (request.kind === "dispose") return dispose(request);
      return Promise.resolve(result(302, "Unknown Backend command"));
    }

    function commandSink(request) {
      rememberGeneration(request);
      var completion = serial.then(function () {
        return nextMainLoop(function () { return execute(request); });
      });
      serial = completion.catch(function () {});
      return completion;
    }

    installedController = Object.freeze({
      uninstall: function () {
        if (removed) return;
        removed = true;
        Object.keys(surfaces).forEach(function (instance) {
          removeSurface(instance);
        });
        surfaceLease = null;
        core.setBackendCommandSink(null);
        installedController = null;
      },
    });
    core.setBackendCommandSink(commandSink);
    return installedController;
  }

  global.VerveWebViewWebBackend = Object.freeze({
    install: install,
  });
})(window);
