package com.tedliou.verve.webview;

import android.content.Context;
import android.content.pm.ApplicationInfo;
import android.net.Uri;
import android.net.http.SslError;
import android.os.Build;
import android.os.Handler;
import android.os.Looper;
import android.view.MotionEvent;
import android.view.View;
import android.view.ViewGroup;
import android.webkit.CookieManager;
import android.webkit.GeolocationPermissions;
import android.webkit.PermissionRequest;
import android.webkit.SafeBrowsingResponse;
import android.webkit.SslErrorHandler;
import android.webkit.ValueCallback;
import android.webkit.WebChromeClient;
import android.webkit.WebResourceRequest;
import android.webkit.WebView;
import android.webkit.WebViewClient;
import java.util.Objects;

/** Android WebView owner behind the narrow asynchronous Platform Backend seam. */
public final class AndroidPlatformBackend {
  private final AndroidBackendRuntime runtime;

  public AndroidPlatformBackend(
      Context context,
      HostLocator hostLocator,
      AndroidBackendRuntime.CompletionSink completionSink,
      AndroidBackendRuntime.HostLostSink hostLostSink,
      DiagnosticSink diagnosticSink) {
    runtime =
        new AndroidBackendRuntime(
            new AndroidPlatform(
                Objects.requireNonNull(context).getApplicationContext(),
                Objects.requireNonNull(hostLocator),
                Objects.requireNonNull(diagnosticSink)),
            completionSink,
            hostLostSink);
  }

  public void submit(AndroidBackendRuntime.Command command) {
    runtime.submit(command);
  }

  /** Non-owning capability supplied by the Binding Target. */
  public interface HostLocator {
    ViewGroup locateCurrentHost();
  }

  public interface DiagnosticSink {
    void onDiagnostic(String detail);
  }

  private static final class AndroidPlatform implements AndroidBackendRuntime.Platform {
    private final Context context;
    private final HostLocator hostLocator;
    private final DiagnosticSink diagnostics;
    private final Handler mainHandler = new Handler(Looper.getMainLooper());

    private AndroidPlatform(Context context, HostLocator hostLocator, DiagnosticSink diagnostics) {
      this.context = context;
      this.hostLocator = hostLocator;
      this.diagnostics = diagnostics;
    }

    @Override
    public void dispatch(Runnable work) {
      mainHandler.post(work);
    }

    @Override
    public AndroidBackendRuntime.Host resolveCurrentHost() {
      ViewGroup host = hostLocator.locateCurrentHost();
      return host == null ? null : new AndroidHost(host);
    }

    @Override
    public AndroidBackendRuntime.Surface createSurface(
        AndroidBackendRuntime.Host host, Runnable hostInvalidated) {
      ViewGroup viewGroup = ((AndroidHost) host).viewGroup;
      return new AndroidSurface(
          viewGroup.getContext(),
          viewGroup,
          hostInvalidated,
          diagnostics,
          (context.getApplicationInfo().flags & ApplicationInfo.FLAG_DEBUGGABLE) != 0);
    }
  }

  private static final class AndroidHost implements AndroidBackendRuntime.Host {
    private final ViewGroup viewGroup;

    private AndroidHost(ViewGroup viewGroup) {
      this.viewGroup = viewGroup;
    }

    @Override
    public boolean isValid() {
      return viewGroup.isAttachedToWindow() && viewGroup.getWindowToken() != null;
    }

    @Override
    public boolean sameHost(AndroidBackendRuntime.Host other) {
      return other instanceof AndroidHost && ((AndroidHost) other).viewGroup == viewGroup;
    }
  }

  private static final class AndroidSurface implements AndroidBackendRuntime.Surface {
    private final ViewGroup host;
    private final WebView webView;
    private final Runnable hostInvalidated;
    private final DiagnosticSink diagnostics;
    private AndroidBackendRuntime.Geometry geometry;
    private boolean destroyed;

    private final View.OnLayoutChangeListener layoutListener =
        (view, left, top, right, bottom, oldLeft, oldTop, oldRight, oldBottom) -> {
          if (geometry != null && !destroyed) {
            applyGeometry(geometry);
          }
        };

    private final View.OnAttachStateChangeListener attachListener =
        new View.OnAttachStateChangeListener() {
          @Override
          public void onViewAttachedToWindow(View view) {}

          @Override
          public void onViewDetachedFromWindow(View view) {
            if (!destroyed) {
              hostInvalidated.run();
            }
          }
        };

    private AndroidSurface(
        Context context,
        ViewGroup host,
        Runnable hostInvalidated,
        DiagnosticSink diagnostics,
        boolean debuggingEnabled) {
      this.host = host;
      this.hostInvalidated = hostInvalidated;
      this.diagnostics = diagnostics;
      webView = new WebView(context);
      configureSecurityPolicy(debuggingEnabled);
    }

    @Override
    public boolean attach() {
      if (destroyed || !host.isAttachedToWindow() || webView.getParent() != null) {
        return false;
      }
      host.addOnLayoutChangeListener(layoutListener);
      host.addOnAttachStateChangeListener(attachListener);
      webView.setFocusable(true);
      webView.setFocusableInTouchMode(true);
      webView.setOnTouchListener(
          (view, event) -> {
            if (event.getActionMasked() == MotionEvent.ACTION_DOWN) {
              view.requestFocus();
            }
            return false;
          });
      host.addView(webView);
      return true;
    }

    @Override
    public boolean applyGeometry(AndroidBackendRuntime.Geometry value) {
      int hostWidth = host.getWidth();
      int hostHeight = host.getHeight();
      if (destroyed || hostWidth <= 0 || hostHeight <= 0) {
        return false;
      }
      geometry = value;
      int left = boundedRound(value.x * hostWidth, 0, hostWidth);
      int top = boundedRound(value.y * hostHeight, 0, hostHeight);
      int right = boundedRound((value.x + value.width) * hostWidth, left, hostWidth);
      int bottom = boundedRound((value.y + value.height) * hostHeight, top, hostHeight);
      webView.setLayoutParams(new ViewGroup.LayoutParams(right - left, bottom - top));
      webView.setX(left);
      webView.setY(top);
      return right > left && bottom > top;
    }

    @Override
    public boolean navigate(String url) {
      if (destroyed || !UrlPolicy.allows(url)) {
        return false;
      }
      webView.loadUrl(url);
      return true;
    }

    @Override
    public void destroy() {
      if (destroyed) {
        return;
      }
      destroyed = true;
      host.removeOnLayoutChangeListener(layoutListener);
      host.removeOnAttachStateChangeListener(attachListener);
      webView.clearFocus();
      webView.stopLoading();
      webView.setOnTouchListener(null);
      if (webView.getParent() instanceof ViewGroup) {
        ((ViewGroup) webView.getParent()).removeView(webView);
      }
      webView.removeAllViews();
      webView.destroy();
    }

    private void configureSecurityPolicy(boolean debuggingEnabled) {
      webView.getSettings().setJavaScriptEnabled(true);
      webView.getSettings().setDomStorageEnabled(true);
      webView.getSettings().setMixedContentMode(android.webkit.WebSettings.MIXED_CONTENT_NEVER_ALLOW);
      webView.getSettings().setAllowFileAccess(false);
      webView.getSettings().setAllowContentAccess(false);
      webView.getSettings().setAllowFileAccessFromFileURLs(false);
      webView.getSettings().setAllowUniversalAccessFromFileURLs(false);
      webView.getSettings().setSupportMultipleWindows(true);
      webView.getSettings().setJavaScriptCanOpenWindowsAutomatically(false);
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
        webView.getSettings().setSafeBrowsingEnabled(true);
      }

      CookieManager cookies = CookieManager.getInstance();
      cookies.setAcceptCookie(true);
      cookies.setAcceptThirdPartyCookies(webView, true);

      WebView.setWebContentsDebuggingEnabled(debuggingEnabled);

      webView.removeJavascriptInterface("searchBoxJavaBridge_");
      webView.removeJavascriptInterface("accessibility");
      webView.removeJavascriptInterface("accessibilityTraversal");
      webView.setWebViewClient(
          Build.VERSION.SDK_INT >= Build.VERSION_CODES.O_MR1
              ? new SafeBrowsingPolicyWebViewClient(diagnostics)
              : new PolicyWebViewClient(diagnostics));
      webView.setWebChromeClient(new DenyingWebChromeClient(diagnostics));
      webView.setDownloadListener(
          (url, userAgent, contentDisposition, mimeType, contentLength) ->
              diagnostics.onDiagnostic("download cancelled by Android Backend policy"));
    }

    private static int boundedRound(double value, int minimum, int maximum) {
      return Math.max(minimum, Math.min(maximum, (int) Math.round(value)));
    }
  }

  private static class PolicyWebViewClient extends WebViewClient {
    protected final DiagnosticSink diagnostics;

    private PolicyWebViewClient(DiagnosticSink diagnostics) {
      this.diagnostics = diagnostics;
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, String url) {
      return rejectIfDisallowed(url);
    }

    @Override
    public boolean shouldOverrideUrlLoading(WebView view, WebResourceRequest request) {
      Uri url = request.getUrl();
      return rejectIfDisallowed(url == null ? null : url.toString());
    }

    @Override
    public void onReceivedSslError(WebView view, SslErrorHandler handler, SslError error) {
      handler.cancel();
      diagnostics.onDiagnostic("TLS certificate error cancelled");
    }

    private boolean rejectIfDisallowed(String url) {
      boolean rejected = !UrlPolicy.allows(url);
      if (rejected) {
        diagnostics.onDiagnostic("top-level navigation cancelled by URL policy");
      }
      return rejected;
    }
  }

  @android.annotation.TargetApi(Build.VERSION_CODES.O_MR1)
  private static final class SafeBrowsingPolicyWebViewClient extends PolicyWebViewClient {
    private SafeBrowsingPolicyWebViewClient(DiagnosticSink diagnostics) {
      super(diagnostics);
    }

    @Override
    public void onSafeBrowsingHit(
        WebView view,
        WebResourceRequest request,
        int threatType,
        SafeBrowsingResponse callback) {
      callback.backToSafety(true);
      diagnostics.onDiagnostic("Safe Browsing blocked a navigation");
    }
  }

  private static final class DenyingWebChromeClient extends WebChromeClient {
    private final DiagnosticSink diagnostics;

    private DenyingWebChromeClient(DiagnosticSink diagnostics) {
      this.diagnostics = diagnostics;
    }

    @Override
    public void onPermissionRequest(PermissionRequest request) {
      request.deny();
      diagnostics.onDiagnostic("browser permission request denied");
    }

    @Override
    public void onGeolocationPermissionsShowPrompt(
        String origin, GeolocationPermissions.Callback callback) {
      callback.invoke(origin, false, false);
      diagnostics.onDiagnostic("geolocation permission denied");
    }

    @Override
    public boolean onShowFileChooser(
        WebView webView,
        ValueCallback<Uri[]> filePathCallback,
        FileChooserParams fileChooserParams) {
      diagnostics.onDiagnostic("file selection denied");
      return false;
    }

    @Override
    public boolean onCreateWindow(
        WebView view, boolean isDialog, boolean isUserGesture, android.os.Message resultMsg) {
      diagnostics.onDiagnostic("popup creation cancelled");
      return false;
    }
  }
}
