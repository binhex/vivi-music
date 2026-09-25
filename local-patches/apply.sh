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

# Android only accepts an in-place update when the update is signed with the same certificate as the
# installed app, so every build must be signed with one pinned keystore. app/build.gradle.kts prefers
# app/persistent-debug.keystore whenever it exists; installing it here keeps CI and local builds on the
# same key. A build without it would sign with a throw-away key and could not update the installed app.
require_pinned_keystore() {
  local source="${PATCH_DIR}/debug.keystore"

  if [[ ! -f "${source}" ]]; then
    echo "Missing ${source}." >&2
    echo "Every build must use this pinned keystore, or Android will refuse to update the installed" >&2
    echo "app. See local-patches/README.md for the one-time keytool command that creates it." >&2
    exit 1
  fi
  if [[ ! -d "${PWD}/app" ]]; then
    echo "No app/ directory below ${PWD}: run this from the root of a vivi-music checkout." >&2
    exit 1
  fi
}

install_pinned_keystore() {
  local target="${PWD}/app/persistent-debug.keystore"

  if [[ -e "${target}" ]]; then
    echo "Replacing the existing app/persistent-debug.keystore with the pinned key."
  fi
  install -m 0644 "${PATCH_DIR}/debug.keystore" "${target}"
  echo "OK   pinned debug keystore installed as app/persistent-debug.keystore"
}

# Validate before patching: refusing afterwards would leave a half-applied tree with no pinned key.
require_pinned_keystore

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

if [[ "${mode}" == "check" ]]; then
  echo "OK   pinned debug keystore present"
else
  install_pinned_keystore
fi
