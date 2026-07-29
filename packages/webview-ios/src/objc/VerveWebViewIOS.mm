#import "packages/webview-ios/src/objc/VerveWebViewIOS.h"

#import <Security/Security.h>
#import <WebKit/WebKit.h>

#include "packages/webview-ios/src/runtime/ios_backend_runtime.h"

#include <cmath>
#include <functional>
#include <memory>
#include <optional>
#include <string>
#include <utility>

namespace ios_backend = verve::webview::ios;

@interface VWLayoutProbe : UIView
@property(nonatomic, copy, nullable) void (^layoutCallback)(void);
@end

@implementation VWLayoutProbe
- (void)layoutSubviews {
  [super layoutSubviews];
  if (self.layoutCallback) {
    self.layoutCallback();
  }
}
@end

@interface VWObservedWebView : WKWebView
@property(nonatomic, copy, nullable) void (^hostInvalidated)(void);
@property(nonatomic) BOOL hostObservationArmed;
@end

@implementation VWObservedWebView
- (void)didMoveToWindow {
  [super didMoveToWindow];
  if (self.hostObservationArmed && self.window == nil && self.hostInvalidated) {
    self.hostInvalidated();
  }
}
@end

static bool VWAllowsURL(NSURL* URL) {
  if (URL == nil || URL.absoluteString == nil) {
    return false;
  }
  return ios_backend::UrlPolicy::Allows(URL.absoluteString.UTF8String ?: "");
}

@interface VWWebViewPolicyDelegate : NSObject <WKNavigationDelegate, WKUIDelegate>
- (instancetype)initWithDiagnosticSink:(VWIOSDiagnosticSink)diagnosticSink;
@end

@implementation VWWebViewPolicyDelegate {
  VWIOSDiagnosticSink _diagnosticSink;
}

- (instancetype)initWithDiagnosticSink:(VWIOSDiagnosticSink)diagnosticSink {
  self = [super init];
  if (self) {
    _diagnosticSink = [diagnosticSink copy];
  }
  return self;
}

- (void)webView:(WKWebView*)webView
    decidePolicyForNavigationAction:(WKNavigationAction*)navigationAction
                    decisionHandler:
                        (void (^)(WKNavigationActionPolicy))decisionHandler {
  if (navigationAction.targetFrame == nil) {
    _diagnosticSink(@"iOS Backend cancelled a request for a new browsing context");
    decisionHandler(WKNavigationActionPolicyCancel);
    return;
  }
  if (navigationAction.targetFrame.mainFrame &&
      !VWAllowsURL(navigationAction.request.URL)) {
    _diagnosticSink(@"iOS Backend cancelled a top-level URL rejected by policy");
    decisionHandler(WKNavigationActionPolicyCancel);
    return;
  }
  if (@available(iOS 14.5, *)) {
    if (navigationAction.shouldPerformDownload) {
      _diagnosticSink(@"iOS Backend cancelled a download");
      decisionHandler(WKNavigationActionPolicyCancel);
      return;
    }
  }
  decisionHandler(WKNavigationActionPolicyAllow);
}

- (void)webView:(WKWebView*)webView
    decidePolicyForNavigationResponse:(WKNavigationResponse*)navigationResponse
                     decisionHandler:
                         (void (^)(WKNavigationResponsePolicy))decisionHandler {
  NSString* contentDisposition = nil;
  if ([navigationResponse.response isKindOfClass:NSHTTPURLResponse.class]) {
    contentDisposition =
        [(NSHTTPURLResponse*)navigationResponse.response
            valueForHTTPHeaderField:@"Content-Disposition"];
  }
  BOOL isAttachment =
      contentDisposition != nil &&
      [contentDisposition rangeOfString:@"attachment"
                                options:NSCaseInsensitiveSearch].location != NSNotFound;
  if (isAttachment || !navigationResponse.canShowMIMEType) {
    _diagnosticSink(@"iOS Backend cancelled a download response");
    decisionHandler(WKNavigationResponsePolicyCancel);
    return;
  }
  decisionHandler(WKNavigationResponsePolicyAllow);
}

- (void)webView:(WKWebView*)webView
    didReceiveAuthenticationChallenge:(NSURLAuthenticationChallenge*)challenge
                    completionHandler:
                        (void (^)(NSURLSessionAuthChallengeDisposition,
                                  NSURLCredential* _Nullable))completionHandler {
  if ([challenge.protectionSpace.authenticationMethod
          isEqualToString:NSURLAuthenticationMethodServerTrust]) {
    SecTrustRef trust = challenge.protectionSpace.serverTrust;
    CFErrorRef error = nullptr;
    BOOL trusted = trust != nullptr && SecTrustEvaluateWithError(trust, &error);
    if (error != nullptr) {
      CFRelease(error);
    }
    if (!trusted) {
      _diagnosticSink(@"iOS Backend cancelled a TLS certificate error");
      completionHandler(NSURLSessionAuthChallengeCancelAuthenticationChallenge, nil);
      return;
    }
  }
  completionHandler(NSURLSessionAuthChallengePerformDefaultHandling, nil);
}

- (void)webView:(WKWebView*)webView
    authenticationChallenge:(NSURLAuthenticationChallenge*)challenge
    shouldAllowDeprecatedTLS:(void (^)(BOOL))decisionHandler API_AVAILABLE(ios(14.0)) {
  _diagnosticSink(@"iOS Backend rejected deprecated TLS");
  decisionHandler(NO);
}

- (nullable WKWebView*)webView:(WKWebView*)webView
    createWebViewWithConfiguration:(WKWebViewConfiguration*)configuration
               forNavigationAction:(WKNavigationAction*)navigationAction
                    windowFeatures:(WKWindowFeatures*)windowFeatures {
  _diagnosticSink(@"iOS Backend cancelled a popup");
  return nil;
}

- (void)webView:(WKWebView*)webView
    requestMediaCapturePermissionForOrigin:(WKSecurityOrigin*)origin
                          initiatedByFrame:(WKFrameInfo*)frame
                                      type:(WKMediaCaptureType)type
                           decisionHandler:(void (^)(WKPermissionDecision))decisionHandler
    API_AVAILABLE(ios(15.0)) {
  _diagnosticSink(@"iOS Backend denied camera or microphone permission");
  decisionHandler(WKPermissionDecisionDeny);
}

- (void)webView:(WKWebView*)webView
    requestDeviceOrientationAndMotionPermissionForOrigin:(WKSecurityOrigin*)origin
                                         initiatedByFrame:(WKFrameInfo*)frame
                                         decisionHandler:
                                             (void (^)(WKPermissionDecision))
                                                 decisionHandler
    API_AVAILABLE(ios(15.0)) {
  _diagnosticSink(@"iOS Backend denied device orientation and motion permission");
  decisionHandler(WKPermissionDecisionDeny);
}

- (void)webView:(WKWebView*)webView
    runOpenPanelWithParameters:(WKOpenPanelParameters*)parameters
              initiatedByFrame:(WKFrameInfo*)frame
             completionHandler:(void (^)(NSArray<NSURL*>* _Nullable URLs))
                                   completionHandler
    API_AVAILABLE(ios(18.4)) {
  _diagnosticSink(@"iOS Backend denied file selection");
  completionHandler(nil);
}

@end

namespace {

class IOSHost final : public ios_backend::Host {
 public:
  explicit IOSHost(UIView* view) : view_(view) {}

  bool IsValid() const override {
    UIView* view = view_;
    return view != nil && view.window != nil;
  }

  bool IsSameHost(const ios_backend::Host& other) const override {
    const auto* ios_host = dynamic_cast<const IOSHost*>(&other);
    return ios_host != nullptr && ios_host->view_ == view_;
  }

  UIView* view() const { return view_; }

 private:
  __weak UIView* view_;
};

class IOSSurface final : public ios_backend::Surface {
 public:
  IOSSurface(
      UIView* host,
      std::function<void()> host_invalidated,
      VWIOSDiagnosticSink diagnostic_sink,
      bool debugging_enabled)
      : host_(host),
        host_invalidated_(std::move(host_invalidated)),
        diagnostic_sink_([diagnostic_sink copy]),
        policy_delegate_([[VWWebViewPolicyDelegate alloc]
            initWithDiagnosticSink:diagnostic_sink_]) {
    WKWebViewConfiguration* configuration = [[WKWebViewConfiguration alloc] init];
    configuration.websiteDataStore = WKWebsiteDataStore.defaultDataStore;
    configuration.userContentController = [[WKUserContentController alloc] init];
    configuration.preferences.javaScriptCanOpenWindowsAutomatically = NO;
    if (@available(iOS 14.0, *)) {
      configuration.defaultWebpagePreferences.allowsContentJavaScript = YES;
    } else {
#pragma clang diagnostic push
#pragma clang diagnostic ignored "-Wdeprecated-declarations"
      configuration.preferences.javaScriptEnabled = YES;
#pragma clang diagnostic pop
    }

    web_view_ = [[VWObservedWebView alloc] initWithFrame:CGRectZero
                                           configuration:configuration];
    web_view_.navigationDelegate = policy_delegate_;
    web_view_.UIDelegate = policy_delegate_;
    web_view_.opaque = YES;
    web_view_.scrollView.keyboardDismissMode =
        UIScrollViewKeyboardDismissModeInteractive;
    if (@available(iOS 16.4, *)) {
      web_view_.inspectable = debugging_enabled;
    } else if (debugging_enabled) {
      diagnostic_sink_(
          @"iOS Backend cannot opt into Web Inspector before iOS 16.4");
    }
    if (@available(iOS 15.0, *)) {
      // Permission delegate callbacks below deny media capture and motion.
    } else {
      diagnostic_sink_(
          @"iOS before 15 has no public per-view media or motion denial "
           "delegate; WebKit and OS prompts retain control");
    }
    if (@available(iOS 18.4, *)) {
      // The file-selection delegate below returns nil.
    } else {
      diagnostic_sink_(
          @"iOS before 18.4 has no public file-selection denial delegate; "
           "the system file picker retains user-mediated control");
    }

    diagnostic_sink_(
        @"iOS Backend retains WebKit secure defaults where mixed-content and "
         "third-party-cookie controls have no public per-view override");
    diagnostic_sink_(
        @"iOS Backend exposes no geolocation or notification grant path; "
         "WebKit and host application policy retain their secure defaults");
  }

  ~IOSSurface() override { Destroy(); }

  bool Attach() override {
    UIView* host = host_;
    if (destroyed_ || host == nil || host.window == nil ||
        web_view_.superview != nil) {
      return false;
    }

    layout_probe_ = [[VWLayoutProbe alloc] initWithFrame:host.bounds];
    layout_probe_.userInteractionEnabled = NO;
    layout_probe_.autoresizingMask =
        UIViewAutoresizingFlexibleWidth | UIViewAutoresizingFlexibleHeight;
    __weak VWObservedWebView* weak_web_view = web_view_;
    __weak VWLayoutProbe* weak_probe = layout_probe_;
    IOSSurface* surface = this;
    layout_probe_.layoutCallback = ^{
      if (weak_web_view != nil && weak_probe != nil && !surface->destroyed_) {
        surface->ApplyCurrentGeometry();
      }
    };
    web_view_.hostInvalidated = ^{
      surface->HostInvalidated();
    };

    [host addSubview:layout_probe_];
    [host addSubview:web_view_];
    web_view_.hostObservationArmed = YES;
    return true;
  }

  bool ApplyGeometry(const ios_backend::Geometry& geometry) override {
    if (destroyed_ || !IsValidGeometry(geometry)) {
      return false;
    }
    geometry_ = geometry;
    has_geometry_ = true;
    return ApplyCurrentGeometry();
  }

  bool Navigate(const std::string& url) override {
    if (destroyed_ || !ios_backend::UrlPolicy::Allows(url)) {
      return false;
    }
    NSString* value = [[NSString alloc] initWithBytes:url.data()
                                               length:url.size()
                                             encoding:NSUTF8StringEncoding];
    NSURL* URL = value == nil ? nil : [NSURL URLWithString:value];
    if (!VWAllowsURL(URL)) {
      return false;
    }
    return [web_view_ loadRequest:[NSURLRequest requestWithURL:URL]] != nil;
  }

  void Focus() override {
    if (!destroyed_) {
      [web_view_ becomeFirstResponder];
    }
  }

  void Destroy() override {
    if (destroyed_) {
      return;
    }
    destroyed_ = true;
    web_view_.hostObservationArmed = NO;
    web_view_.hostInvalidated = nil;
    layout_probe_.layoutCallback = nil;
    [web_view_ resignFirstResponder];
    [web_view_ stopLoading];
    web_view_.navigationDelegate = nil;
    web_view_.UIDelegate = nil;
    [web_view_ removeFromSuperview];
    [layout_probe_ removeFromSuperview];
    web_view_ = nil;
    layout_probe_ = nil;
    policy_delegate_ = nil;
    host_ = nil;
  }

 private:
  static bool IsValidGeometry(const ios_backend::Geometry& geometry) {
    return std::isfinite(geometry.x) && std::isfinite(geometry.y) &&
           std::isfinite(geometry.width) && std::isfinite(geometry.height) &&
           geometry.x >= 0.0 && geometry.y >= 0.0 &&
           geometry.width > 0.0 && geometry.height > 0.0 &&
           geometry.x <= 1.0 && geometry.y <= 1.0 &&
           geometry.x + geometry.width <= 1.0 &&
           geometry.y + geometry.height <= 1.0;
  }

  bool ApplyCurrentGeometry() {
    UIView* host = host_;
    if (!has_geometry_ || host == nil || CGRectIsEmpty(host.bounds)) {
      return false;
    }
    const CGRect bounds = host.bounds;
    CGRect requested = CGRectMake(
        CGRectGetMinX(bounds) + geometry_.x * CGRectGetWidth(bounds),
        CGRectGetMinY(bounds) + geometry_.y * CGRectGetHeight(bounds),
        geometry_.width * CGRectGetWidth(bounds),
        geometry_.height * CGRectGetHeight(bounds));
    CGRect clipped = CGRectIntersection(bounds, requested);
    if (CGRectIsNull(clipped) || CGRectIsEmpty(clipped)) {
      return false;
    }
    web_view_.frame = clipped;
    return true;
  }

  void HostInvalidated() {
    if (!destroyed_ && host_invalidated_) {
      host_invalidated_();
    }
  }

  __strong UIView* host_;
  std::function<void()> host_invalidated_;
  __strong VWIOSDiagnosticSink diagnostic_sink_;
  __strong VWWebViewPolicyDelegate* policy_delegate_;
  __strong VWObservedWebView* web_view_;
  __strong VWLayoutProbe* layout_probe_;
  ios_backend::Geometry geometry_{};
  bool has_geometry_ = false;
  bool destroyed_ = false;
};

class IOSPlatform final : public ios_backend::Platform {
 public:
  IOSPlatform(
      VWIOSHostLocator host_locator,
      VWIOSDiagnosticSink diagnostic_sink,
      bool debugging_enabled)
      : host_locator_([host_locator copy]),
        diagnostic_sink_([diagnostic_sink copy]),
        debugging_enabled_(debugging_enabled) {}

  void Dispatch(std::function<void()> work) override {
    auto owned_work =
        std::make_shared<std::function<void()>>(std::move(work));
    dispatch_async(dispatch_get_main_queue(), ^{
      (*owned_work)();
    });
  }

  std::shared_ptr<ios_backend::Host> ResolveCurrentHost() override {
    UIView* host = host_locator_();
    return host == nil ? nullptr : std::make_shared<IOSHost>(host);
  }

  std::shared_ptr<ios_backend::Surface> CreateSurface(
      const std::shared_ptr<ios_backend::Host>& host,
      std::function<void()> host_invalidated) override {
    auto ios_host = std::dynamic_pointer_cast<IOSHost>(host);
    if (!ios_host || !ios_host->IsValid()) {
      return nullptr;
    }
    return std::make_shared<IOSSurface>(
        ios_host->view(),
        std::move(host_invalidated),
        diagnostic_sink_,
        debugging_enabled_);
  }

 private:
  __strong VWIOSHostLocator host_locator_;
  __strong VWIOSDiagnosticSink diagnostic_sink_;
  bool debugging_enabled_;
};

ios_backend::CommandKind CommandKindFromPublic(VWIOSBackendCommandKind kind) {
  switch (kind) {
    case VWIOSBackendCommandInitialize:
      return ios_backend::CommandKind::kInitialize;
    case VWIOSBackendCommandOpen:
      return ios_backend::CommandKind::kOpen;
    case VWIOSBackendCommandClose:
      return ios_backend::CommandKind::kClose;
    case VWIOSBackendCommandDispose:
      return ios_backend::CommandKind::kDispose;
  }
  return ios_backend::CommandKind::kUnknown;
}

}  // namespace

@implementation VWIOSPlatformBackend {
  std::unique_ptr<ios_backend::IOSBackendRuntime> _runtime;
}

- (instancetype)initWithHostLocator:(VWIOSHostLocator)hostLocator
                     completionSink:(VWIOSCompletionSink)completionSink
                       hostLostSink:(VWIOSHostLostSink)hostLostSink
                     diagnosticSink:(VWIOSDiagnosticSink)diagnosticSink
                   debuggingEnabled:(BOOL)debuggingEnabled {
  self = [super init];
  if (self) {
    auto platform = std::make_shared<IOSPlatform>(
        hostLocator, diagnosticSink, debuggingEnabled);
    VWIOSCompletionSink owned_completion = [completionSink copy];
    VWIOSHostLostSink owned_host_lost = [hostLostSink copy];
    _runtime = std::make_unique<ios_backend::IOSBackendRuntime>(
        platform,
        [owned_completion](const ios_backend::Completion& value) {
          NSString* diagnostic = value.diagnostic_detail.empty()
              ? nil
              : [[NSString alloc]
                    initWithBytes:value.diagnostic_detail.data()
                           length:value.diagnostic_detail.size()
                         encoding:NSUTF8StringEncoding];
          owned_completion(
              value.instance,
              value.operation,
              value.generation,
              value.code,
              diagnostic);
        },
        [owned_host_lost](std::uint64_t instance) { owned_host_lost(instance); });
  }
  return self;
}

- (void)submitCommand:(VWIOSBackendCommandKind)kind
             instance:(uint64_t)instance
            operation:(uint64_t)operation
           generation:(uint32_t)generation
                  URL:(nullable NSString*)URL
             geometry:(nullable const VWIOSSurfaceGeometry*)geometry {
  std::optional<ios_backend::Geometry> runtime_geometry;
  if (geometry != nullptr) {
    runtime_geometry = ios_backend::Geometry{
        geometry->x, geometry->y, geometry->width, geometry->height};
  }
  std::string payload = URL == nil ? "" : (URL.UTF8String ?: "");
  _runtime->Submit(ios_backend::Command{
      CommandKindFromPublic(kind),
      instance,
      operation,
      generation,
      std::move(payload),
      runtime_geometry,
  });
}

@end
