#!/usr/bin/env bash
set -euo pipefail

manifest=
declare -a payloads=()
for file in "$@"; do
  case "${file}" in
    *browser_consumer_identity.txt)
      manifest="${file}"
      ;;
    *.js|*.wasm)
      payloads+=("${file}")
      ;;
  esac
done

test -n "${manifest}"
test "$(wc -l < "${manifest}")" -eq 5
test "${#payloads[@]}" -eq 5

for payload in "${payloads[@]}"; do
  sha256sum "${payload}"
done | LC_ALL=C sort
