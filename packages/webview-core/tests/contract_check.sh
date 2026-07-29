#!/usr/bin/env bash
set -euo pipefail

stamp="${TEST_SRCDIR}/${TEST_WORKSPACE}/packages/webview-core/api_contract.verified"
test -f "${stamp}"
test "$(cat "${stamp}")" = "api-contract 1.0.0 verified"
