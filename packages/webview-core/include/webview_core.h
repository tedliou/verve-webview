#ifndef VERVE_WEBVIEW_CORE_H
#define VERVE_WEBVIEW_CORE_H

#include <stdint.h>
#include "webview_api_contract.h"

#ifdef __cplusplus
extern "C" {
#endif

#define VERVE_WEBVIEW_ABI_VERSION UINT32_C(1)
#define VERVE_WEBVIEW_CAP_BACKEND_COMMAND_SINK UINT64_C(1)
#define VERVE_WEBVIEW_CAP_COMPLETION_EVENT_SINK UINT64_C(2)
#define VERVE_WEBVIEW_CAP_DIAGNOSTIC_SINK UINT64_C(4)
#define VERVE_WEBVIEW_CAPABILITIES UINT64_C(7)

typedef uint64_t verve_webview_instance_handle;
typedef uint64_t verve_webview_operation_handle;

typedef enum verve_webview_operation_kind {
  VERVE_WEBVIEW_OPERATION_INITIALIZE = 1,
  VERVE_WEBVIEW_OPERATION_OPEN = 2,
  VERVE_WEBVIEW_OPERATION_CLOSE = 3,
  VERVE_WEBVIEW_OPERATION_DISPOSE = 4,
} verve_webview_operation_kind;

typedef struct verve_webview_abi_info {
  uint32_t struct_size;
  uint32_t abi_version;
  uint64_t capabilities;
} verve_webview_abi_info;

typedef struct verve_webview_geometry {
  double x;
  double y;
  double width;
  double height;
} verve_webview_geometry;

typedef struct verve_webview_backend_request {
  uint32_t struct_size;
  uint32_t operation_kind;
  verve_webview_instance_handle instance;
  verve_webview_operation_handle operation;
  uint32_t generation;
  uint32_t has_geometry;
  verve_webview_bytes_view payload;
  verve_webview_geometry geometry;
} verve_webview_backend_request;

typedef struct verve_webview_completion {
  uint32_t struct_size;
  uint32_t code;
  verve_webview_instance_handle instance;
  verve_webview_operation_handle operation;
  uint32_t generation;
  uint32_t reserved;
  verve_webview_bytes_view diagnostic_detail;
} verve_webview_completion;

typedef struct verve_webview_completion_event {
  uint32_t struct_size;
  uint32_t operation_kind;
  verve_webview_instance_handle instance;
  verve_webview_operation_handle operation;
  verve_webview_result result;
} verve_webview_completion_event;

typedef void (*verve_webview_backend_command_sink)(
    void *user_data,
    const verve_webview_backend_request *request);
typedef void (*verve_webview_completion_event_sink)(
    void *user_data,
    const verve_webview_completion_event *event);
typedef void (*verve_webview_diagnostic_sink)(
    void *user_data,
    verve_webview_instance_handle instance,
    verve_webview_operation_handle operation,
    verve_webview_bytes_view detail);

typedef struct verve_webview_instance_config {
  uint32_t struct_size;
  uint32_t abi_version;
  uint64_t required_capabilities;
  void *user_data;
  verve_webview_backend_command_sink backend_command_sink;
  verve_webview_completion_event_sink completion_event_sink;
  verve_webview_diagnostic_sink diagnostic_sink;
} verve_webview_instance_config;

uint32_t verve_webview_get_abi_info(verve_webview_abi_info *out_info);
uint32_t verve_webview_create_instance(
    const verve_webview_instance_config *config,
    verve_webview_instance_handle *out_instance);
uint32_t verve_webview_initialize(
    verve_webview_instance_handle instance,
    verve_webview_bytes_view options,
    verve_webview_operation_handle *out_operation);
uint32_t verve_webview_open(
    verve_webview_instance_handle instance,
    verve_webview_bytes_view url,
    const verve_webview_geometry *geometry,
    verve_webview_operation_handle *out_operation);
uint32_t verve_webview_close(
    verve_webview_instance_handle instance,
    verve_webview_operation_handle *out_operation);
uint32_t verve_webview_dispose(
    verve_webview_instance_handle instance,
    verve_webview_operation_handle *out_operation);
uint32_t verve_webview_complete(const verve_webview_completion *completion);
uint32_t verve_webview_report_host_lost(verve_webview_instance_handle instance);

#ifdef __cplusplus
}
#endif

#endif
