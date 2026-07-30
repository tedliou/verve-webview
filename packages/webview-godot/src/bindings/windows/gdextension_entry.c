#include <stdint.h>

#if defined(_WIN32)
#define VERVE_GDEXPORT __declspec(dllexport)
#else
#define VERVE_GDEXPORT __attribute__((visibility("default")))
#endif

typedef uint8_t GDExtensionBool;
typedef void *GDExtensionClassLibraryPtr;
typedef void *(*GDExtensionInterfaceGetProcAddress)(const char *name);
typedef void (*GDExtensionInitializationFunction)(
    void *userdata, int32_t initialization_level);

typedef struct GDExtensionInitialization {
  int32_t minimum_initialization_level;
  void *userdata;
  GDExtensionInitializationFunction initialize;
  GDExtensionInitializationFunction deinitialize;
} GDExtensionInitialization;

/*
 * Empty engine-registration payload. The GDScript Adapter remains the public
 * API; this loadable Binding-owned library provides Godot's native lifecycle
 * entry and ships beside the reusable Windows Platform Backend DLL.
 */
VERVE_GDEXPORT GDExtensionBool verve_webview_library_init(
    GDExtensionInterfaceGetProcAddress get_proc_address,
    GDExtensionClassLibraryPtr library,
    GDExtensionInitialization *initialization) {
  (void)get_proc_address;
  (void)library;
  if (initialization == 0) {
    return 0;
  }
  initialization->minimum_initialization_level = 0;
  initialization->userdata = 0;
  initialization->initialize = 0;
  initialization->deinitialize = 0;
  return 1;
}
