#!/usr/bin/env bash
set -euo pipefail

for required in \
  WebView.cs \
  WebViewOptions.cs \
  WebViewContract.g.cs \
  adapter.content-manifest.json \
  adapter.fragment-manifest.json
do
  found=false
  for entry in "$@"
  do
    if [[ "${entry##*/}" == "${required}" ]]; then
      found=true
      break
    fi
  done
  if [[ "${found}" != true ]]; then
    echo "missing Unity Adapter entry: ${required}" >&2
    exit 1
  fi
done

entries="$*"
if [[ "${entries}" == *"verve_webview_windows.dll"* ]] ||
   [[ "${entries}" == *"verve_webview_web_backend.js"* ]] ||
   [[ "${entries}" == *"VerveWebViewIOS"* ]] ||
   [[ "${entries}" == *"verve-webview.aar"* ]]
then
  echo "Unity Adapter must not contain a concrete Platform Backend" >&2
  exit 1
fi
