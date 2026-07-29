#!/usr/bin/env bash
set -euo pipefail

if [[ -n "${TEST_SRCDIR:-}" && -n "${TEST_WORKSPACE:-}" ]]; then
  repository_root="${TEST_SRCDIR}/${TEST_WORKSPACE}"
else
  repository_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
fi
windows_temp_raw="$(cmd.exe /d /c echo %TEMP% 2>/dev/null | tr -d '\r')"
windows_temp="$(wslpath -u "${windows_temp_raw}")"
test_root="$(mktemp -d "${windows_temp}/verve-unity-editmode.XXXXXX")"
project_root="${test_root}/project"
package_root="${project_root}/Packages/com.tedliou.verve-webview"
results_path="${test_root}/editmode-results.xml"

cleanup() {
  rm -rf "${test_root}"
}
trap cleanup EXIT

mkdir -p "${project_root}/Assets" "${project_root}/Packages" "${project_root}/ProjectSettings"
mkdir -p "${package_root}/Runtime" "${package_root}/Tests/Editor"
cp "${repository_root}/packages/webview-unity/tests/EditModeProject/Packages/manifest.json" "${project_root}/Packages/manifest.json"
cp "${repository_root}/packages/webview-unity/tests/EditModeProject/ProjectSettings/ProjectVersion.txt" "${project_root}/ProjectSettings/ProjectVersion.txt"
cp "${repository_root}/packages/webview-unity/tests/package.json" "${package_root}/package.json"
cp "${repository_root}/packages/webview-unity/tests/Runtime/Verve.WebView.asmdef" "${package_root}/Runtime/Verve.WebView.asmdef"
cp "${repository_root}/packages/webview-core/generated/unity/WebViewContract.g.cs" "${package_root}/Runtime/WebViewContract.g.cs"
cp "${repository_root}"/packages/webview-unity/src/adapter/*.cs "${package_root}/Runtime/"
cp "${repository_root}/packages/webview-unity/tests/EditMode/Verve.WebView.Tests.asmdef" "${package_root}/Tests/Editor/Verve.WebView.Tests.asmdef"
cp "${repository_root}"/packages/webview-unity/tests/EditMode/*.cs "${package_root}/Tests/Editor/"

project_windows="$(wslpath -w "${project_root}")"
results_windows="$(wslpath -w "${results_path}")"
set +e
unity.exe --non-interactive test "${project_windows}" \
  --mode EditMode \
  --output "${results_windows}" \
  --editor-version 2021.3.45f2 \
  --timeout 300 \
  -- -nographics -logFile -
unity_status=$?
set -e

test -f "${results_path}"
cp "${results_path}" /tmp/verve-unity-editmode-results.xml
if [[ ${unity_status} -ne 0 ]]; then
  exit "${unity_status}"
fi
grep -F 'failed="0"' "${results_path}"
