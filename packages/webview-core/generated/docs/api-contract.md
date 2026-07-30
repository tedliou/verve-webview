# WebView SDK API Contract 1.0.0

Generated from `api-contract.yaml`. Expected failures are returned as WebView Result values.

## Operations

- `initialize`
- `open`
- `close`
- `dispose`

## Public Error Codes

| ID | Canonical name | Applicable operations | State effect | Caller action |
|---:|---|---|---|---|
| 0 | `ok` | initialize, open, close, dispose | `operation_success` | The operation completed successfully. Continue. |
| 100 | `invalid_options` | initialize | `unchanged` | Initialization options are invalid. Correct the options before retrying. |
| 101 | `invalid_url` | open | `unchanged` | The direct open URL violates syntax or v1 URL policy. Correct the URL before retrying. |
| 102 | `invalid_geometry` | open | `unchanged` | Surface geometry is non-finite, out of range, or non-positive. Correct the geometry before retrying. |
| 200 | `not_initialized` | open, close | `unchanged` | Open or close was called before successful initialization. Initialize successfully before retrying. |
| 201 | `already_initialized` | initialize | `unchanged` | Initialize was called on an initialized SDK Instance. Reuse the initialized SDK Instance. |
| 202 | `operation_in_progress` | initialize, open, close | `unchanged` | A strict single-flight operation is active. Wait for it to finish. |
| 203 | `disposed` | initialize, open, close, dispose | `disposed` | The SDK Instance is terminal and cannot be reused. Create a new SDK Instance. |
| 204 | `surface_not_open` | close | `unchanged` | Close was called without an open WebView Surface. Open a surface before closing. |
| 205 | `surface_in_use` | open | `unchanged` | Another SDK Instance owns the application Surface Lease. Close or dispose the current lease owner before retrying. |
| 300 | `host_unavailable` | initialize, open | `operation_failure` | No usable engine host currently exists. Retry after host availability changes. |
| 301 | `host_lost` | initialize, open, close, dispose | `surface_cleaned_and_initialized_closed` | The host was permanently lost while an operation was active. Resolve a new host and retry when appropriate. |
| 302 | `backend_failure` | initialize, open, close, dispose | `operation_failure` | A platform operation failed without a more actionable portable classification. Inspect diagnostics and retry only when appropriate. |
| 303 | `cleanup_failed` | dispose | `disposed` | Dispose cleanup failed, but the SDK Instance is terminal. Report diagnostics; do not reuse the instance. |
| 400 | `core_load_failed` | initialize | `operation_failure` | The shared Core could not be loaded. Repair or reinstall the distribution. |
| 401 | `abi_mismatch` | initialize, open, close, dispose | `operation_failure` | ABI version, capability negotiation, or a received wire ID is incompatible. Install one atomic compatible distribution. |
| 402 | `runtime_unavailable` | initialize, open | `operation_failure` | A required platform browser runtime is missing or insufficient. Install or update that runtime. |
| 403 | `unsupported_environment` | initialize | `operation_failure` | The engine, platform, architecture, toolchain, or Web Runtime is unsupported. Use a declared supported environment. |
| 404 | `distribution_invalid` | initialize | `operation_failure` | Required payload or manifest content is missing, corrupt, or inconsistent. Reinstall a verified distribution. |
| 500 | `internal_failure` | initialize, open, close, dispose | `invalidated` | Core or Engine Adapter violated an internal invariant. Report the defect rather than retrying. |
