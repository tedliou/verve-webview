#include "webview_core.h"
#include "webview_lifecycle_conformance.h"

#include <assert.h>
#include <stddef.h>
#include <stdint.h>
#include <string.h>

_Static_assert(sizeof(verve_webview_instance_handle) == 8, "fixed-width instance handle");
_Static_assert(sizeof(verve_webview_operation_handle) == 8, "fixed-width operation handle");
_Static_assert(sizeof(((verve_webview_completion *)0)->generation) == 4,
               "fixed-width generation");
_Static_assert(offsetof(verve_webview_completion, diagnostic_detail) % 8 == 0,
               "stable envelope alignment");

typedef struct test_context {
  uint32_t backend_count;
  uint32_t event_count;
  uint32_t diagnostic_count;
  uint32_t last_event_code;
  uint32_t response_code;
  verve_webview_completion last_completion;
} test_context;

static void on_event(
    void *user_data,
    const verve_webview_completion_event *event) {
  test_context *context = (test_context *)user_data;
  assert(event != NULL);
  assert(event->struct_size == sizeof(*event));
  context->event_count += 1;
  context->last_event_code = event->result.code;
}

static void on_diagnostic(
    void *user_data,
    verve_webview_instance_handle instance,
    verve_webview_operation_handle operation,
    verve_webview_bytes_view detail) {
  test_context *context = (test_context *)user_data;
  assert(instance != 0);
  assert(operation != 0);
  assert(detail.data != NULL);
  assert(detail.length != 0);
  context->diagnostic_count += 1;
}

static void on_backend(
    void *user_data,
    const verve_webview_backend_request *request) {
  test_context *context = (test_context *)user_data;
  assert(request != NULL);
  assert(request->struct_size == sizeof(*request));
  context->backend_count += 1;
  context->last_completion = (verve_webview_completion){
      .struct_size = sizeof(verve_webview_completion),
      .code = context->response_code,
      .instance = request->instance,
      .operation = request->operation,
      .generation = request->generation,
      .diagnostic_detail = {NULL, 0},
  };

  /* Reentrant completion proves Core invokes the backend without its lock held. */
  assert(verve_webview_complete(&context->last_completion) == VERVE_WEBVIEW_OK);
}

int main(void) {
  assert(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTOR_COUNT == 24);
  assert(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[0].is_legal == 1);
  assert(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[1].is_legal == 0);
  assert(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[8].is_legal == 1);
  assert(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[14].is_legal == 1);

  verve_webview_abi_info info = {0};
  assert(verve_webview_get_abi_info(&info) == VERVE_WEBVIEW_OK);
  assert(info.struct_size == sizeof(info));
  assert(info.abi_version == VERVE_WEBVIEW_ABI_VERSION);
  assert(info.capabilities == VERVE_WEBVIEW_CAPABILITIES);

  test_context context = {0};
  verve_webview_instance_config incompatible = {
      .struct_size = sizeof(verve_webview_instance_config),
      .abi_version = VERVE_WEBVIEW_ABI_VERSION + 1,
      .user_data = &context,
      .backend_command_sink = on_backend,
      .completion_event_sink = on_event,
  };
  verve_webview_instance_handle instance = 0;
  assert(verve_webview_create_instance(&incompatible, &instance) ==
         VERVE_WEBVIEW_ABI_MISMATCH);
  assert(instance == 0);

  verve_webview_instance_config config = {
      .struct_size = sizeof(verve_webview_instance_config),
      .abi_version = VERVE_WEBVIEW_ABI_VERSION,
      .required_capabilities = VERVE_WEBVIEW_CAPABILITIES,
      .user_data = &context,
      .backend_command_sink = on_backend,
      .completion_event_sink = on_event,
      .diagnostic_sink = on_diagnostic,
  };
  assert(verve_webview_create_instance(&config, &instance) == VERVE_WEBVIEW_OK);
  assert(instance != 0);
  assert((instance >> 32) == 1);

  static const uint8_t options[] = "{}";
  verve_webview_operation_handle operation = 0;
  assert(verve_webview_initialize(
             instance,
             (verve_webview_bytes_view){options, sizeof(options) - 1},
             NULL) == VERVE_WEBVIEW_ABI_MISMATCH);
  assert(context.backend_count == 0);
  assert(verve_webview_initialize(
             instance,
             (verve_webview_bytes_view){options, sizeof(options) - 1},
             &operation) == VERVE_WEBVIEW_OK);
  assert(operation != 0);
  assert((operation >> 32) == 1);
  assert(context.backend_count == 1);
  assert(context.event_count == 1);
  assert(context.last_event_code == VERVE_WEBVIEW_OK);

  /* A duplicate backend completion is diagnostic-only. */
  assert(verve_webview_complete(&context.last_completion) == VERVE_WEBVIEW_OK);
  assert(context.event_count == 1);
  assert(context.diagnostic_count == 1);

  assert(verve_webview_open(
             instance,
             (verve_webview_bytes_view){NULL, 8},
             NULL,
             &operation) == VERVE_WEBVIEW_INVALID_URL);
  assert(context.backend_count == 1);

  static const uint8_t url[] = "https://example.com";
  verve_webview_geometry invalid_geometry = {0.0, 0.0, 0.0, 1.0};
  assert(verve_webview_open(
             instance,
             (verve_webview_bytes_view){url, sizeof(url) - 1},
             &invalid_geometry,
             &operation) == VERVE_WEBVIEW_INVALID_GEOMETRY);
  assert(context.backend_count == 1);

  context.response_code = UINT32_C(999999);
  assert(verve_webview_open(
             instance,
             (verve_webview_bytes_view){url, sizeof(url) - 1},
             NULL,
             &operation) == VERVE_WEBVIEW_OK);
  assert(context.event_count == 2);
  assert(context.last_event_code == VERVE_WEBVIEW_ABI_MISMATCH);
  context.response_code = VERVE_WEBVIEW_OK;

  assert(verve_webview_dispose(instance, &operation) == VERVE_WEBVIEW_OK);
  assert((operation >> 32) == 2);
  assert(context.backend_count == 3);
  assert(context.event_count == 3);
  assert(verve_webview_initialize(
             instance,
             (verve_webview_bytes_view){options, sizeof(options) - 1},
             &operation) == VERVE_WEBVIEW_DISPOSED);
  return 0;
}
