#ifndef VERVE_WEBVIEW_WINDOWS_PLATFORM_BACKEND_H_
#define VERVE_WEBVIEW_WINDOWS_PLATFORM_BACKEND_H_

#include <stdint.h>
#include <windows.h>

#ifdef VERVE_WEBVIEW_WINDOWS_EXPORTS
#define VW_WINDOWS_API __declspec(dllexport)
#else
#define VW_WINDOWS_API __declspec(dllimport)
#endif

extern "C" {

typedef HWND (*VWWindowsHostLocator)(void* context);
typedef void (*VWWindowsWork)(void* context);
typedef void (*VWWindowsDispatcher)(
    void* context, VWWindowsWork work, void* work_context);
typedef void (*VWWindowsCompletionSink)(
    void* context, uint64_t instance, uint64_t operation, uint32_t generation,
    uint32_t code, const char* diagnostic_detail);
typedef void (*VWWindowsHostLostSink)(void* context, uint64_t instance);
typedef void (*VWWindowsDiagnosticSink)(void* context, const char* detail);

typedef struct VWWindowsSurfaceGeometry {
  double x;
  double y;
  double width;
  double height;
} VWWindowsSurfaceGeometry;

typedef struct VWWindowsBackend VWWindowsBackend;

VW_WINDOWS_API VWWindowsBackend* verve_webview_windows_create(
    VWWindowsHostLocator host_locator, VWWindowsDispatcher dispatcher,
    VWWindowsCompletionSink completion_sink,
    VWWindowsHostLostSink host_lost_sink,
    VWWindowsDiagnosticSink diagnostic_sink, void* callback_context,
    int debugging_enabled);

VW_WINDOWS_API void verve_webview_windows_submit(
    VWWindowsBackend* backend, uint32_t kind, uint64_t instance,
    uint64_t operation, uint32_t generation, const char* url,
    const VWWindowsSurfaceGeometry* geometry);

VW_WINDOWS_API void verve_webview_windows_destroy(VWWindowsBackend* backend);

}

#endif
