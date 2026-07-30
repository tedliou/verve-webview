/* @generated from api-contract.yaml; do not edit. */
#ifndef VERVE_WEBVIEW_LIFECYCLE_CONFORMANCE_H
#define VERVE_WEBVIEW_LIFECYCLE_CONFORMANCE_H
#include <stdint.h>

typedef struct verve_webview_lifecycle_legality_vector {
  uint32_t operation;
  uint32_t state;
  uint32_t is_legal;
} verve_webview_lifecycle_legality_vector;

static const verve_webview_lifecycle_legality_vector VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[] = {
  {1, 1, 1},
  {1, 2, 0},
  {1, 3, 0},
  {1, 4, 0},
  {1, 5, 0},
  {1, 6, 0},
  {2, 1, 0},
  {2, 2, 1},
  {2, 3, 1},
  {2, 4, 0},
  {2, 5, 0},
  {2, 6, 0},
  {3, 1, 0},
  {3, 2, 0},
  {3, 3, 1},
  {3, 4, 0},
  {3, 5, 0},
  {3, 6, 0},
  {4, 1, 1},
  {4, 2, 1},
  {4, 3, 1},
  {4, 4, 0},
  {4, 5, 0},
  {4, 6, 0},
};

#define VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTOR_COUNT \
+  (sizeof(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS) / \
+   sizeof(VERVE_WEBVIEW_LIFECYCLE_LEGALITY_VECTORS[0]))

#endif
