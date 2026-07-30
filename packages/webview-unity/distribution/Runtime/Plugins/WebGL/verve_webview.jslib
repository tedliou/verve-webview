mergeInto(LibraryManager.library, {
  VerveWebView_CoreReady: function () {
    return typeof VerveWebViewCore === "object" ? 1 : 0;
  }
});
