#!/usr/bin/env bash
set -euo pipefail

wasm_count=0
bindgen_js_count=0
facade_count=0

for file in "$@"; do
  case "${file}" in
    *_bg.wasm)
      wasm_count=$((wasm_count + 1))
      ;;
    */verve_webview_core.js)
      bindgen_js_count=$((bindgen_js_count + 1))
      ;;
    */verve_webview_core_facade.js)
      facade_count=$((facade_count + 1))
      ;;
  esac
done

test "${wasm_count}" -eq 1
test "${bindgen_js_count}" -eq 1
test "${facade_count}" -eq 1
