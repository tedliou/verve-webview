// @generated from api-contract.yaml; do not edit.
export const PublicErrorCode = Object.freeze({
  ok: 0,
  invalid_options: 100,
  invalid_url: 101,
  invalid_geometry: 102,
  not_initialized: 200,
  already_initialized: 201,
  operation_in_progress: 202,
  disposed: 203,
  surface_not_open: 204,
  surface_in_use: 205,
  host_unavailable: 300,
  host_lost: 301,
  backend_failure: 302,
  cleanup_failed: 303,
  core_load_failed: 400,
  abi_mismatch: 401,
  runtime_unavailable: 402,
  unsupported_environment: 403,
  distribution_invalid: 404,
  internal_failure: 500,
});

export const operations = Object.freeze(["initialize", "open", "close", "dispose"]);

export const isSuccess = result => result.code === PublicErrorCode.ok;
