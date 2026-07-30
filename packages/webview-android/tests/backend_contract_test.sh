#!/usr/bin/env bash
set -euo pipefail

manifest=
metadata=
aar=
for path in "$@"; do
  case "$path" in
    *.txt) manifest="$path" ;;
    *runtime-metadata.json) metadata="$path" ;;
    *.aar) aar="$path" ;;
  esac
done

test -n "$manifest"
test -n "$metadata"
test -n "$aar"

test "$(grep -c '^platform=android$' "$manifest")" -eq 1
test "$(grep -c '^payload=release/arm64-v8a/verve-webview.aar$' "$manifest")" -eq 1
test "$(grep -c '^payload=verification/x86_64/verve-webview.aar$' "$manifest")" -eq 1
grep -q '"java_release": 11' "$metadata"
grep -q '"min_sdk": 24' "$metadata"

members="$(unzip -Z1 "$aar")"
grep -qx 'AndroidManifest.xml' <<<"$members"
grep -qx 'classes.jar' <<<"$members"
unzip -p "$aar" AndroidManifest.xml | grep -q 'minSdkVersion.*24'

class_file="$(mktemp)"
trap 'rm -f "$class_file"' EXIT
unzip -p "$aar" classes.jar >"${class_file}.jar"
unzip -p "${class_file}.jar" \
  com/tedliou/verve/webview/AndroidPlatformBackend.class >"$class_file"
test "$(od -An -t u1 -j 6 -N 2 "$class_file" | tr -d ' ')" = "055"
rm -f "${class_file}.jar"
