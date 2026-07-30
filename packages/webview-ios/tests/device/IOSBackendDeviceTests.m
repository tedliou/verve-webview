#import <WebKit/WebKit.h>
#import <XCTest/XCTest.h>

#import "packages/webview-ios/src/objc/VerveWebViewIOS.h"

@interface IOSBackendDeviceTests : XCTestCase
@end

@implementation IOSBackendDeviceTests

- (WKWebView*)findWebViewInView:(UIView*)view {
  if ([view isKindOfClass:WKWebView.class]) {
    return (WKWebView*)view;
  }
  for (UIView* child in view.subviews) {
    WKWebView* found = [self findWebViewInView:child];
    if (found != nil) {
      return found;
    }
  }
  return nil;
}

- (void)testLifecycleGeometryPolicyAndCleanupUseARealWKWebView {
  UIWindow* window = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 320, 480)];
  UIViewController* controller = [[UIViewController alloc] init];
  window.rootViewController = controller;
  [window makeKeyAndVisible];
  [controller.view layoutIfNeeded];
  UIView* host = [[UIView alloc] initWithFrame:CGRectMake(0, 0, 320, 480)];
  [controller.view addSubview:host];

  XCTestExpectation* openCompletion = [self expectationWithDescription:@"open"];
  XCTestExpectation* closeCompletion = [self expectationWithDescription:@"close"];
  __block BOOL completedInline = NO;
  __block BOOL submitReturned = NO;
  VWIOSPlatformBackend* backend = [[VWIOSPlatformBackend alloc]
      initWithHostLocator:^UIView* {
        return host;
      }
      completionSink:^(uint64_t instance, uint64_t operation, uint32_t generation,
                       uint32_t code, NSString* detail) {
        completedInline = !submitReturned;
        XCTAssertEqual(code, 0u);
        if (operation == 2) {
          [openCompletion fulfill];
        } else if (operation == 3) {
          [closeCompletion fulfill];
        }
      }
      hostLostSink:^(uint64_t instance) {
        XCTFail(@"host must remain valid during lifecycle test");
      }
      diagnosticSink:^(NSString* detail) {
      }
      debuggingEnabled:NO];

  VWIOSSurfaceGeometry geometry = {0.25, 0.20, 0.50, 0.60};
  [backend submitCommand:VWIOSBackendCommandOpen
                instance:1
               operation:2
              generation:1
                     URL:@"https://example.test/"
                geometry:&geometry];
  submitReturned = YES;
  XCTAssertEqual(
      [XCTWaiter waitForExpectations:@[ openCompletion ] timeout:5.0],
      XCTWaiterResultCompleted);
  XCTAssertFalse(completedInline);

  WKWebView* webView = [self findWebViewInView:host];
  XCTAssertNotNil(webView);
  XCTAssertEqualWithAccuracy(webView.frame.origin.x, 80.0, 0.5);
  XCTAssertEqualWithAccuracy(webView.frame.origin.y, 96.0, 0.5);
  XCTAssertEqualWithAccuracy(webView.frame.size.width, 160.0, 0.5);
  XCTAssertEqualWithAccuracy(webView.frame.size.height, 288.0, 0.5);
  XCTAssertEqual(
      webView.configuration.websiteDataStore, WKWebsiteDataStore.defaultDataStore);
  XCTAssertFalse(
      webView.configuration.preferences.javaScriptCanOpenWindowsAutomatically);
  XCTAssertEqual(
      webView.configuration.userContentController.userScripts.count, 0u);
  if (@available(iOS 16.4, *)) {
    XCTAssertFalse(webView.inspectable);
  }
  if (@available(iOS 15.0, *)) {
    __block WKPermissionDecision mediaDecision = WKPermissionDecisionPrompt;
    [(id<WKUIDelegate>)webView.UIDelegate
                    webView:webView
        requestMediaCapturePermissionForOrigin:nil
                              initiatedByFrame:nil
                                          type:WKMediaCaptureTypeCameraAndMicrophone
                               decisionHandler:^(WKPermissionDecision decision) {
                                 mediaDecision = decision;
                               }];
    XCTAssertEqual(mediaDecision, WKPermissionDecisionDeny);

    __block WKPermissionDecision motionDecision = WKPermissionDecisionPrompt;
    [(id<WKUIDelegate>)webView.UIDelegate
                                webView:webView
        requestDeviceOrientationAndMotionPermissionForOrigin:nil
                                             initiatedByFrame:nil
                                             decisionHandler:^(
                                                 WKPermissionDecision decision) {
                                               motionDecision = decision;
                                             }];
    XCTAssertEqual(motionDecision, WKPermissionDecisionDeny);
  }
  if (@available(iOS 18.4, *)) {
    __block NSArray<NSURL*>* selectedURLs = @[ [NSURL URLWithString:@"file:///tmp"] ];
    [(id<WKUIDelegate>)webView.UIDelegate
                    webView:webView
        runOpenPanelWithParameters:nil
                  initiatedByFrame:nil
                 completionHandler:^(NSArray<NSURL*>* URLs) {
                   selectedURLs = URLs;
                 }];
    XCTAssertNil(selectedURLs);
  }

  host.bounds = CGRectMake(0, 0, 640, 480);
  [host layoutIfNeeded];
  XCTAssertEqualWithAccuracy(webView.frame.origin.x, 160.0, 0.5);
  XCTAssertEqualWithAccuracy(webView.frame.size.width, 320.0, 0.5);
  XCTAssertEqualWithAccuracy(webView.frame.origin.y, 96.0, 0.5);
  XCTAssertEqualWithAccuracy(webView.frame.size.height, 288.0, 0.5);

  [backend submitCommand:VWIOSBackendCommandClose
                instance:1
               operation:3
              generation:1
                     URL:nil
                geometry:nil];
  XCTAssertEqual(
      [XCTWaiter waitForExpectations:@[ closeCompletion ] timeout:5.0],
      XCTWaiterResultCompleted);
  XCTAssertNil([self findWebViewInView:host]);
  window.hidden = YES;
}

- (void)testInvalidURLIsRejectedWithoutCreatingAWKWebView {
  UIWindow* window = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 320, 480)];
  UIViewController* controller = [[UIViewController alloc] init];
  window.rootViewController = controller;
  [window makeKeyAndVisible];

  XCTestExpectation* completion = [self expectationWithDescription:@"rejection"];
  VWIOSPlatformBackend* backend = [[VWIOSPlatformBackend alloc]
      initWithHostLocator:^UIView* {
        return controller.view;
      }
      completionSink:^(uint64_t instance, uint64_t operation, uint32_t generation,
                       uint32_t code, NSString* detail) {
        XCTAssertEqual(code, 302u);
        [completion fulfill];
      }
      hostLostSink:^(uint64_t instance) {
        XCTFail(@"invalid URL must not create a host-owned Surface");
      }
      diagnosticSink:^(NSString* detail) {
      }
      debuggingEnabled:NO];

  [backend submitCommand:VWIOSBackendCommandOpen
                instance:10
               operation:11
              generation:1
                     URL:@"file:///tmp/page.html"
                geometry:nil];
  XCTAssertEqual(
      [XCTWaiter waitForExpectations:@[ completion ] timeout:5.0],
      XCTWaiterResultCompleted);
  XCTAssertNil([self findWebViewInView:controller.view]);
  window.hidden = YES;
}

- (void)testActualHostDetachmentReportsHostLostAndCleansUp {
  UIWindow* window = [[UIWindow alloc] initWithFrame:CGRectMake(0, 0, 320, 480)];
  UIViewController* controller = [[UIViewController alloc] init];
  window.rootViewController = controller;
  [window makeKeyAndVisible];

  XCTestExpectation* openCompletion = [self expectationWithDescription:@"open"];
  XCTestExpectation* hostLost = [self expectationWithDescription:@"host lost"];
  VWIOSPlatformBackend* backend = [[VWIOSPlatformBackend alloc]
      initWithHostLocator:^UIView* {
        return controller.view;
      }
      completionSink:^(uint64_t instance, uint64_t operation, uint32_t generation,
                       uint32_t code, NSString* detail) {
        XCTAssertEqual(code, 0u);
        [openCompletion fulfill];
      }
      hostLostSink:^(uint64_t instance) {
        XCTAssertEqual(instance, 20u);
        [hostLost fulfill];
      }
      diagnosticSink:^(NSString* detail) {
      }
      debuggingEnabled:NO];

  [backend submitCommand:VWIOSBackendCommandOpen
                instance:20
               operation:21
              generation:1
                     URL:@"https://example.test/"
                geometry:nil];
  XCTAssertEqual(
      [XCTWaiter waitForExpectations:@[ openCompletion ] timeout:5.0],
      XCTWaiterResultCompleted);
  XCTAssertNotNil([self findWebViewInView:controller.view]);

  window.rootViewController = nil;
  XCTAssertEqual(
      [XCTWaiter waitForExpectations:@[ hostLost ] timeout:5.0],
      XCTWaiterResultCompleted);
  XCTAssertNil([self findWebViewInView:controller.view]);
  window.hidden = YES;
}

@end
