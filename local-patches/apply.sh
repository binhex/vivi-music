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
# upstream-drift canary in CI. Patches are applied in filename order, so one patch may build on lines an
# earlier patch adds; --check therefore validates them cumulatively in a throwaway index while leaving
# the worktree untouched.
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

# Check mode applies every patch in filename order to a throwaway index seeded from HEAD, because a later
# patch may build on lines an earlier one adds. Seeding from HEAD keeps the check honest - the index holds
# exactly what a clean checkout would have - and nothing is written to the worktree, which is what makes
# the weekly drift canary safe to run.
check_index=""
cleanup() {
  if [[ -n "${check_index}" ]]; then
    rm -rf "$(dirname "${check_index}")"
  fi
}
trap cleanup EXIT
if [[ "${mode}" == "check" ]]; then
  check_index="$(mktemp -d "${TMPDIR:-/tmp}/vivi-apply-check.XXXXXX")/index"
  # A fresh `git init` tree has no HEAD to seed from (the signing-key fixtures are like that), so fall
  # back to the worktree contents; either way the index describes the state the patches are checked
  # against, and neither writes to the worktree or to the real index.
  if ! GIT_INDEX_FILE="${check_index}" git read-tree HEAD 2>/dev/null; then
    GIT_INDEX_FILE="${check_index}" git add -A
  fi
fi

for patch in "${patches[@]}"; do
  name="$(basename "${patch}")"
  if [[ "${mode}" == "check" ]]; then
    GIT_INDEX_FILE="${check_index}" git apply --cached --verbose "${patch}"
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
