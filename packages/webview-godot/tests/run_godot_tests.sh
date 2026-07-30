#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${TEST_SRCDIR:-}" && -n "${TEST_WORKSPACE:-}" ]]; then
	workspace_root="${TEST_SRCDIR}/${TEST_WORKSPACE}"
	package_root="${workspace_root}/packages/webview-godot"
else
	package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
	workspace_root="$(cd "${package_root}/../.." && pwd)"
fi
temporary_root="${ISSUE29_TEST_TMP_ROOT:-${workspace_root}/.issue29-godot-tests}"
mkdir -p "${temporary_root}"
project="$(mktemp -d "${temporary_root}/project.XXXXXX")"
trap 'rm -rf "${project}"' EXIT
addon="${project}/addons/verve_webview"
mkdir -p "${addon}"

cp "${package_root}/tests/project/project.godot" "${project}/project.godot"
cp "${package_root}/tests/project/test_runner.gd" "${project}/test_runner.gd"
cp "${package_root}/tests/project/readonly_mutation.gd" "${project}/readonly_mutation.gd"
cp "${workspace_root}/packages/webview-core/generated/godot/webview_contract.gd" \
	"${addon}/webview_contract.gd"
for source in "${package_root}"/src/adapter/*.gd; do
	cp "${source}" "${addon}/$(basename "${source}")"
done

godot_bin="${GODOT_BIN:-}"
if [[ -z "${godot_bin}" ]]; then
	godot_bin="$(command -v godot4 || command -v godot || true)"
fi
if [[ -z "${godot_bin}" ]]; then
	echo "Godot editor binary not found; set GODOT_BIN" >&2
	exit 1
fi

project_path="${project}"
if [[ "${godot_bin}" == *.exe ]]; then
	project_path="$(wslpath -w "${project}")"
fi

set +e
runtime_output="$(
	"${godot_bin}" \
		--headless \
		--path "${project_path}" \
		--script test_runner.gd \
		--no-header 2>&1
)"
runtime_status=$?
set -e
if [[ ${runtime_status} -ne 0 ]] \
	|| ! grep -q "ISSUE29_GODOT_ADAPTER_TESTS_OK" <<<"${runtime_output}" \
	|| grep -Eq "SCRIPT ERROR|^ERROR:" <<<"${runtime_output}"; then
	echo "${runtime_output}" >&2
	echo "Godot Adapter runtime suite failed" >&2
	exit 1
fi
echo "${runtime_output}" | grep "ISSUE29_GODOT_ADAPTER_TESTS_OK"

set +e
readonly_output="$(
	"${godot_bin}" \
		--headless \
		--path "${project_path}" \
		--script readonly_mutation.gd \
		--no-header 2>&1
)"
readonly_status=$?
set -e
if [[ ${readonly_status} -ne 0 ]] \
	|| ! grep -q "ISSUE29_GODOT_IMMUTABLE_RESULT_OK" <<<"${readonly_output}" \
	|| [[ "$(grep -ci "read-only" <<<"${readonly_output}")" -lt 3 ]]; then
	echo "${readonly_output}" >&2
	echo "WebViewResult properties did not preserve immutable semantics" >&2
	exit 1
fi

echo "${readonly_output}" | grep "ISSUE29_GODOT_IMMUTABLE_RESULT_OK"
