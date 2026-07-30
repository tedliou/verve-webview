#!/usr/bin/env bash
set -euo pipefail

manifest=
metadata=
xcframework=
for path in "$@"; do
  case "$path" in
    *.txt) manifest="$path" ;;
    *runtime-metadata.json) metadata="$path" ;;
    *.xcframework.zip) xcframework="$path" ;;
  esac
done

test -n "$manifest"
test -n "$metadata"
test -n "$xcframework"

test "$(grep -c '^platform=ios$' "$manifest")" -eq 1
test "$(grep -c '^payload=release/ios/VerveWebViewIOS.xcframework.zip$' "$manifest")" -eq 1
grep -q '"minimum_ios_version": "13.0"' "$metadata"
grep -q '"rules_apple_version": "4.5.3"' "$metadata"
grep -q '"variant": "device"' "$metadata"
grep -q '"variant": "simulator"' "$metadata"

members="$(unzip -Z1 "$xcframework")"
grep -qx 'VerveWebViewIOS.xcframework/Info.plist' <<<"$members"
grep -qx \
  'VerveWebViewIOS.xcframework/ios-arm64/VerveWebViewIOS.framework/Headers/VerveWebViewIOS.h' \
  <<<"$members"
grep -qx \
  'VerveWebViewIOS.xcframework/ios-arm64/VerveWebViewIOS.framework/VerveWebViewIOS' \
  <<<"$members"
grep -qx \
  'VerveWebViewIOS.xcframework/ios-arm64_x86_64-simulator/VerveWebViewIOS.framework/Headers/VerveWebViewIOS.h' \
  <<<"$members"
grep -qx \
  'VerveWebViewIOS.xcframework/ios-arm64_x86_64-simulator/VerveWebViewIOS.framework/VerveWebViewIOS' \
  <<<"$members"

root_plist="$(unzip -p "$xcframework" VerveWebViewIOS.xcframework/Info.plist | plutil -p -)"
grep -q '"LibraryIdentifier" => "ios-arm64"' <<<"$root_plist"
grep -q '"LibraryIdentifier" => "ios-arm64_x86_64-simulator"' <<<"$root_plist"
