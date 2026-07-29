#ifndef VERVE_WEBVIEW_IOS_PLATFORM_BACKEND_H_
#define VERVE_WEBVIEW_IOS_PLATFORM_BACKEND_H_

#import <Foundation/Foundation.h>
#import <UIKit/UIKit.h>

NS_ASSUME_NONNULL_BEGIN

typedef NS_ENUM(uint32_t, VWIOSBackendCommandKind) {
  VWIOSBackendCommandInitialize = 1,
  VWIOSBackendCommandOpen = 2,
  VWIOSBackendCommandClose = 3,
  VWIOSBackendCommandDispose = 4,
};

typedef struct VWIOSSurfaceGeometry {
  double x;
  double y;
  double width;
  double height;
} VWIOSSurfaceGeometry;

typedef UIView* _Nullable (^VWIOSHostLocator)(void);
typedef void (^VWIOSCompletionSink)(
    uint64_t instance,
    uint64_t operation,
    uint32_t generation,
    uint32_t code,
    NSString* _Nullable diagnosticDetail);
typedef void (^VWIOSHostLostSink)(uint64_t instance);
typedef void (^VWIOSDiagnosticSink)(NSString* detail);

/// WKWebView owner behind the narrow asynchronous Platform Backend seam.
///
/// The Host Locator is non-owning and is invoked on the iOS main thread for
/// each UI operation. Accepted commands never invoke completion inline.
@interface VWIOSPlatformBackend : NSObject

- (instancetype)init NS_UNAVAILABLE;

- (instancetype)initWithHostLocator:(VWIOSHostLocator)hostLocator
                     completionSink:(VWIOSCompletionSink)completionSink
                       hostLostSink:(VWIOSHostLostSink)hostLostSink
                     diagnosticSink:(VWIOSDiagnosticSink)diagnosticSink
                   debuggingEnabled:(BOOL)debuggingEnabled
    NS_DESIGNATED_INITIALIZER;

- (void)submitCommand:(VWIOSBackendCommandKind)kind
             instance:(uint64_t)instance
            operation:(uint64_t)operation
           generation:(uint32_t)generation
                  URL:(nullable NSString*)URL
             geometry:(nullable const VWIOSSurfaceGeometry*)geometry;

@end

NS_ASSUME_NONNULL_END

#endif  // VERVE_WEBVIEW_IOS_PLATFORM_BACKEND_H_
