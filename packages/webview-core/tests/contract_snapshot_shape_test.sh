#!/usr/bin/env bash
set -euo pipefail

root="${TEST_SRCDIR}/${TEST_WORKSPACE}/packages/webview-core"
groups=(rust native web unity godot docs conformance)

for group in "${groups[@]}"; do
  test -d "${root}/generated/${group}"
  test "$(find -L "${root}/generated/${group}" -type f | wc -l)" -gt 0
done

test -f "${root}/generated/native/webview_api_contract.h"
test -f "${root}/generated/native/webview_lifecycle_conformance.h"
test "$(find -L "${root}/generated" -type f | wc -l)" -eq 8
