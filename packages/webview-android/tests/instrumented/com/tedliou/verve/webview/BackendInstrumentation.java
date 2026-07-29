package com.tedliou.verve.webview;

import android.app.Activity;
import android.app.Instrumentation;
import android.content.Intent;
import android.os.Build;
import android.os.Bundle;
import android.view.ViewGroup;
import android.widget.FrameLayout;
import android.webkit.CookieManager;
import android.webkit.WebSettings;
import android.webkit.WebView;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicReference;

public final class BackendInstrumentation extends Instrumentation {
  @Override
  public void onStart() {
    new Thread(
            () -> {
              Bundle result = new Bundle();
              try {
                runBackendContract();
                result.putString("stream", "Android Backend instrumentation passed\n");
                finish(Activity.RESULT_OK, result);
              } catch (Throwable error) {
                result.putString("stream", "Android Backend instrumentation failed: " + error + "\n");
                finish(Activity.RESULT_CANCELED, result);
              }
            },
            "verve-webview-instrumentation")
        .start();
  }

  private void runBackendContract() throws Exception {
    Intent intent = new Intent().setClassName(
        getTargetContext().getPackageName(),
        "com.tedliou.verve.webview.BackendTestActivity");
    intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
    Activity activity = startActivitySync(intent);
    waitForIdleSync();
    FrameLayout host =
        (FrameLayout)
            activity.getWindow().getDecorView().findViewWithTag("verve-webview-test-host");
    check(host != null, "test host must be discoverable");

    AtomicReference<AndroidBackendRuntime.Completion> completion = new AtomicReference<>();
    CountDownLatch completionLatch = new CountDownLatch(1);
    CountDownLatch hostLostLatch = new CountDownLatch(1);
    AndroidPlatformBackend backend =
        new AndroidPlatformBackend(
            activity,
            () -> host,
            value -> {
              completion.set(value);
              completionLatch.countDown();
            },
            ignored -> hostLostLatch.countDown(),
            ignored -> {});

    backend.submit(
        AndroidBackendRuntime.Command.open(
            1L,
            2L,
            1,
            "https://example.test/",
            new AndroidBackendRuntime.Geometry(0.25, 0.20, 0.50, 0.60)));
    await(completionLatch, "open completion");
    check(completion.get().code == AndroidBackendRuntime.OK, "open must succeed");

    AtomicReference<WebView> webViewRef = new AtomicReference<>();
    runOnMainSync(
        () -> {
          check(host.getChildCount() == 1, "one WebView must be attached");
          WebView webView = (WebView) host.getChildAt(0);
          webViewRef.set(webView);
          WebSettings settings = webView.getSettings();
          check(settings.getJavaScriptEnabled(), "JavaScript must be enabled");
          check(settings.getDomStorageEnabled(), "DOM Storage must be enabled");
          check(
              settings.getMixedContentMode() == WebSettings.MIXED_CONTENT_NEVER_ALLOW,
              "mixed content must be blocked");
          check(!settings.getAllowFileAccess(), "file access must be disabled");
          check(!settings.getAllowContentAccess(), "content access must be disabled");
          check(!settings.getAllowFileAccessFromFileURLs(), "file cross-origin access disabled");
          check(
              !settings.getAllowUniversalAccessFromFileURLs(),
              "universal file access must be disabled");
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            check(settings.getSafeBrowsingEnabled(), "Safe Browsing must be enabled");
          }
          check(CookieManager.getInstance().acceptCookie(), "first-party cookies enabled");
          check(
              CookieManager.getInstance().acceptThirdPartyCookies(webView),
              "third-party cookies proactively enabled");
          if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            check(
                webView
                    .getWebViewClient()
                    .shouldOverrideUrlLoading(webView, "mailto:test@example.test"),
                "external schemes must be cancelled");
            check(
                !webView
                    .getWebViewClient()
                    .shouldOverrideUrlLoading(webView, "http://example.test/"),
                "valid HTTP navigation must stay in the Surface");
            check(
                !webView.getWebChromeClient().onCreateWindow(webView, false, true, null),
                "popups must be cancelled");
          }
          check(webView.getWidth() <= host.getWidth(), "geometry must clip to host");
        });

    backend.submit(AndroidBackendRuntime.Command.close(1L, 3L, 1));
    awaitNewCompletion(completion, 3L);
    runOnMainSync(() -> check(host.getChildCount() == 0, "close must remove WebView"));

    CountDownLatch reopenLatch = new CountDownLatch(1);
    AndroidPlatformBackend hostLossBackend =
        new AndroidPlatformBackend(
            activity,
            () -> host,
            ignored -> reopenLatch.countDown(),
            ignored -> hostLostLatch.countDown(),
            ignored -> {});
    hostLossBackend.submit(
        AndroidBackendRuntime.Command.open(
            4L, 5L, 1, "https://example.test/reopen", null));
    await(reopenLatch, "reopen completion");
    runOnMainSync(() -> activity.finish());
    await(hostLostLatch, "host-loss notification");
  }

  private static void await(CountDownLatch latch, String description) throws Exception {
    check(latch.await(15, TimeUnit.SECONDS), "timed out waiting for " + description);
  }

  private static void awaitNewCompletion(
      AtomicReference<AndroidBackendRuntime.Completion> completion, long operation)
      throws Exception {
    long deadline = System.nanoTime() + TimeUnit.SECONDS.toNanos(15);
    while (System.nanoTime() < deadline) {
      AndroidBackendRuntime.Completion value = completion.get();
      if (value != null && value.operation == operation) {
        return;
      }
      Thread.sleep(10);
    }
    throw new AssertionError("timed out waiting for operation " + operation);
  }

  private static void check(boolean condition, String message) {
    if (!condition) {
      throw new AssertionError(message);
    }
  }
}
