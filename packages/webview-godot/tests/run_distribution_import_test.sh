#!/usr/bin/env bash
set -euo pipefail

if [[ $# -ne 2 ]]; then
	echo "usage: $0 ADAPTER_FRAGMENT_TREE WEB_FRAGMENT_TREE" >&2
	exit 2
fi
adapter_tree="$(realpath "$1")"
web_tree="$(realpath "$2")"
package_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
workspace_root="$(cd "${package_root}/../.." && pwd)"
temporary_root="${ISSUE30_TEST_TMP_ROOT:-${workspace_root}/.issue30-godot-tests}"
mkdir -p "${temporary_root}"
project="$(mktemp -d "${temporary_root}/project.XXXXXX")"
trap 'chmod -R u+w "${project}" 2>/dev/null || true; rm -rf "${project}"' EXIT

cp -R --no-preserve=mode "${adapter_tree}/." "${project}/"
cp -R --no-preserve=mode "${web_tree}/." "${project}/"
if [[ ! -f "${project}/addons/verve_webview/export/android_export_plugin.gd" ]]; then
	mkdir -p "${project}/addons/verve_webview/export"
	cp "${package_root}/src/bindings/android/android_export_plugin.gd" \
		"${project}/addons/verve_webview/export/android_export_plugin.gd"
fi
cp "${package_root}"/tests/distribution_project/* "${project}/"
mkdir -p "${project}/Build/Web"

godot_bin="${GODOT_BIN:-}"
if [[ -z "${godot_bin}" ]]; then
	echo "Godot editor binary not found; set GODOT_BIN" >&2
	exit 1
fi
project_path="${project}"
if [[ "${godot_bin}" == *.exe ]]; then
	project_path="$(wslpath -w "${project}")"
fi

"${godot_bin}" --headless --path "${project_path}" --editor --quit
"${godot_bin}" --headless --path "${project_path}" \
	--export-release Web "${project_path}\\Build\\Web\\index.html"

grep -q '<!-- VERVE_WEBVIEW_CORE -->' "${project}/Build/Web/index.html"
for payload in \
	api-contract.js \
	verve_webview_core.js \
	verve_webview_core_bg.wasm \
	verve_webview_core_facade.js \
	verve_webview_web_backend.js; do
	cmp \
		"${project}/addons/verve_webview/bin/web/${payload}" \
		"${project}/Build/Web/VerveWebViewCore/${payload}"
done
grep -q 'version="0.0.0-pre.0"' \
	"${project}/addons/verve_webview/plugin.cfg"
echo "ISSUE30_GODOT_IMPORT_EXPORT_OK"
