# API Contract generation

`packages/webview-core/api-contract.yaml` is the only semantic source for the
four WebView Core operations, lifecycle effects, WebView Result, and permanent
v1 Public Error Code catalogue. The JSON encoding is valid YAML 1.2 and lets
the generator reject unsupported YAML features instead of accepting ambiguous
input.

Update committed snapshots:

```sh
bazel run //packages/webview-core:update_api_contract -- update
```

Verify schema invariants, unique IDs and names, permanent/reserved ID
preservation, deterministic regeneration, and byte-for-byte committed
snapshots:

```sh
bazel test \
  //packages/webview-core:contract_check \
  //packages/webview-core:contract_rejection_test \
  //packages/webview-core:contract_snapshot_shape_test
```

Validate the canonical graph and visibility:

```sh
bazel query \
  'set(
    //packages/webview-core:api_contract
    //packages/webview-core:core_native
    //packages/webview-core:core_web
    //packages/webview-android:backend
    //packages/webview-ios:backend
    //packages/webview-windows:backend
    //packages/webview-web:backend
    //packages/webview-unity:*
    //packages/webview-godot:*
  )'
```

After an intentional update, the following scoped check must print nothing:

```sh
git status --short -- \
  packages build compatibility MODULE.bazel MODULE.bazel.lock .bazelversion
```

The public `sdk` targets are release-only. They require the canonical
aggregation platform and the one version input:

```sh
bazel build //packages/webview-unity:sdk //packages/webview-godot:sdk \
  --platforms=//build/platforms:canonical_aggregation \
  --//build:release_version=1.0.0
```

The fixed transition target keeps the architecture label
`//build/platforms:canonical_aggregation`. Its private constraint value is
named `canonical_aggregation_capability` because Bazel does not allow a
`platform()` and `constraint_value()` to share one label.
