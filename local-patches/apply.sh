#!/usr/bin/env bash
#
# Applies every patch in this directory to the current working tree.
#
# Run it from the root of a clean checkout of upstream main:
#
#   local-patches/apply.sh --check   # dry run, changes nothing
#   local-patches/apply.sh           # apply for real
#
# It exits non-zero on the first patch that does not apply, which is what makes it double as the
# upstream-drift canary in CI.
set -euo pipefail

PATCH_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
readonly PATCH_DIR

if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  echo "Run this from inside a git checkout of vivi-music (upstream main)." >&2
  exit 1
fi

mode="apply"
if [[ "${1:-}" == "--check" ]]; then
  mode="check"
fi

shopt -s nullglob
patches=("${PATCH_DIR}"/*.patch)
if (( ${#patches[@]} == 0 )); then
  echo "No patches found in ${PATCH_DIR}" >&2
  exit 1
fi

for patch in "${patches[@]}"; do
  name="$(basename "${patch}")"
  if [[ "${mode}" == "check" ]]; then
    git apply --check --verbose "${patch}"
    echo "OK   ${name} (applies)"
  else
    git apply --verbose "${patch}"
    echo "OK   ${name} (applied)"
  fi
done
