#!/usr/bin/env bash
set -euo pipefail

root="${TEST_SRCDIR}/${TEST_WORKSPACE}/packages/webview-core"
generator="${root}/update_api_contract"
contract="${root}/api-contract.yaml"
registry="${root}/error-id-registry.json"
snapshots="${root}/generated"

duplicate_contract="${TEST_TMPDIR}/duplicate-id.yaml"
sed '0,/"id": 100/s//"id": 0/' "${contract}" > "${duplicate_contract}"
if "${generator}" verify "${duplicate_contract}" "${registry}" "${snapshots}" \
  "${TEST_TMPDIR}/duplicate.stamp" 2> "${TEST_TMPDIR}/duplicate.err"; then
  echo "duplicate public error ID was accepted" >&2
  exit 1
fi
grep -F "duplicate public error ID 0" "${TEST_TMPDIR}/duplicate.err"

reserved_registry="${TEST_TMPDIR}/reserved-registry.json"
sed '0,/"status": "active"/s//"status": "reserved"/' \
  "${registry}" > "${reserved_registry}"
if "${generator}" verify "${contract}" "${reserved_registry}" "${snapshots}" \
  "${TEST_TMPDIR}/reserved.stamp" 2> "${TEST_TMPDIR}/reserved.err"; then
  echo "reserved public error ID was reused" >&2
  exit 1
fi
grep -F "reserved ID 0 was reused" "${TEST_TMPDIR}/reserved.err"

malformed_contract="${TEST_TMPDIR}/malformed.yaml"
sed '/"result": {/,/^  },$/d' "${contract}" > "${malformed_contract}"
if "${generator}" verify "${malformed_contract}" "${registry}" "${snapshots}" \
  "${TEST_TMPDIR}/malformed.stamp" 2> "${TEST_TMPDIR}/malformed.err"; then
  echo "contract without result schema was accepted" >&2
  exit 1
fi
grep -F 'missing "result"' "${TEST_TMPDIR}/malformed.err"
