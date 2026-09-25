#!/usr/bin/env bash
#
# Regression test for "app not installed because app conflicts with an existing package".
#
# Android only accepts an in-place update when the new APK is signed with the same certificate as the
# installed app, so signing is pinned to local-patches/debug.keystore, which apply.sh installs into the
# build tree as app/persistent-debug.keystore. This suite checks that plumbing without Gradle, the
# Android SDK or a device.
#
#   local-patches/tests/test-signing-key-stability.sh
#
# The pinned keystore is not created here; it is supplied by the fork owner (see README). While it is
# absent the suite reports PENDING for the one check that needs it, and the CI build fails loudly,
# because apply.sh refuses to patch a tree without it.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
readonly REPO_ROOT
readonly PATCH_DIR="${REPO_ROOT}/local-patches"
readonly WORKFLOW="${REPO_ROOT}/.github/workflows/local-build.yml"
readonly PIN_FILE="${PATCH_DIR}/signing-cert.sha256"
readonly WORK_DIR="${TMPDIR:-/tmp}/vivi-signing-key-stability"
readonly FIXTURE_KEYSTORE="test fixture, deliberately not a keystore"

PASSED=0
FAILED=0
PENDING=0

ok() { printf 'PASS     %s\n' "$1"; PASSED=$((PASSED + 1)); }
not_ok() { printf 'FAIL     %s\n' "$1"; FAILED=$((FAILED + 1)); }
pending() { printf 'PENDING  %s\n' "$1"; PENDING=$((PENDING + 1)); }

new_tree() {
  local target="$1"
  mkdir -p "${target}"
  git -C "${REPO_ROOT}" archive HEAD | tar -x -C "${target}"
  git -C "${target}" init -q
}

new_fixture() {
  local fixture="$1" with_keystore="$2"
  mkdir -p "${fixture}"
  cp "${PATCH_DIR}/apply.sh" "${fixture}/apply.sh"
  cp "${PATCH_DIR}"/*.patch "${fixture}/"
  chmod +x "${fixture}/apply.sh"
  if [[ "${with_keystore}" == "yes" ]]; then
    printf '%s\n' "${FIXTURE_KEYSTORE}" >"${fixture}/debug.keystore"
  fi
}

apply_into() {
  local fixture="$1" tree="$2" log="$3"
  shift 3
  ( cd "${tree}" && "${fixture}/apply.sh" "$@" ) >"${log}" 2>&1
}

# The debug signing configuration decides which key signs a debug APK.
debug_signing_config() {
  awk '/getByName\("debug"\)/{found=1} found{print} found && /^    \}/{exit}' "$1"
}

# The storeFile expression of that configuration, with comments removed so that prose cannot satisfy
# the assertion below - only the expression that actually selects the key counts.
debug_signing_store() {
  debug_signing_config "$1" |
    sed 's|//.*||' |
    awk '/^[[:space:]]*storeFile/{collect=1} collect{print} collect && /\?[:]/{exit}'
}

rm -rf "${WORK_DIR}"
mkdir -p "${WORK_DIR}"

readonly FIXTURE_WITH="${WORK_DIR}/fixture-with-keystore"
readonly FIXTURE_WITHOUT="${WORK_DIR}/fixture-without-keystore"
readonly TREE_ONE="${WORK_DIR}/tree-one"
readonly TREE_TWO="${WORK_DIR}/tree-two"
readonly TREE_CHECK="${WORK_DIR}/tree-check"

new_fixture "${FIXTURE_WITH}" yes
new_fixture "${FIXTURE_WITHOUT}" no
new_tree "${TREE_ONE}"
new_tree "${TREE_TWO}"
new_tree "${TREE_CHECK}"

if apply_into "${FIXTURE_WITH}" "${TREE_ONE}" "${WORK_DIR}/apply-one.log"; then
  if [[ -f "${TREE_ONE}/app/persistent-debug.keystore" ]] &&
    cmp -s "${TREE_ONE}/app/persistent-debug.keystore" "${FIXTURE_WITH}/debug.keystore"; then
    ok "apply.sh installs the pinned keystore as app/persistent-debug.keystore"
  else
    not_ok "apply.sh did not install the pinned keystore (see ${WORK_DIR}/apply-one.log)"
  fi
else
  not_ok "apply.sh failed on a well-formed tree (see ${WORK_DIR}/apply-one.log)"
fi

if apply_into "${FIXTURE_WITHOUT}" "${TREE_TWO}" "${WORK_DIR}/apply-two.log"; then
  not_ok "apply.sh patched a tree even though the pinned keystore was missing"
elif grep -q "debug.keystore" "${WORK_DIR}/apply-two.log"; then
  ok "apply.sh refuses to patch when the pinned keystore is missing"
else
  not_ok "apply.sh failed for an unrelated reason (see ${WORK_DIR}/apply-two.log)"
fi

# Refusing after patching would leave a half-applied tree with no pinned key, so the check has to
# happen first.
if [[ -e "${TREE_TWO}/app/src/main/kotlin/com/music/vivi/playback/DownloadRecovery.kt" ]]; then
  not_ok "apply.sh patched the tree before noticing the missing keystore"
else
  ok "apply.sh refuses before patching, so a missing key cannot leave a half-applied tree"
fi

signing_store="$(debug_signing_store "${TREE_ONE}/app/build.gradle.kts" | tr '\n' ' ')"
if grep -qF 'storeFile = file("persistent-debug.keystore")' <<<"${signing_store}" &&
  grep -qF '.takeIf { it.exists() }' <<<"${signing_store}" &&
  grep -qF '?:' <<<"${signing_store}" &&
  grep -qF '.android/debug.keystore' <<<"${signing_store}"; then
  ok "the debug signing config prefers the pinned keystore, with a per-machine fallback"
else
  not_ok "the debug signing config does not prefer app/persistent-debug.keystore: ${signing_store}"
fi

# Falling back is survivable but must not be silent: that build cannot update a pinned install.
if grep -qF "logger.warn" <<<"$(debug_signing_config "${TREE_ONE}/app/build.gradle.kts" | sed 's|//.*||')"; then
  ok "the signing config warns when it falls back to the per-machine key"
else
  not_ok "the signing config falls back to a per-machine key without a warning"
fi

# upstream-drift.yml runs apply.sh --check weekly; it must notice a missing keystore too, because that
# state means no build can produce an updatable APK.
if apply_into "${FIXTURE_WITH}" "${TREE_CHECK}" "${WORK_DIR}/check-with.log" --check; then
  ok "apply.sh --check passes when the pinned keystore is present"
else
  not_ok "apply.sh --check failed with the pinned keystore present (see ${WORK_DIR}/check-with.log)"
fi

if apply_into "${FIXTURE_WITHOUT}" "${TREE_CHECK}" "${WORK_DIR}/check-without.log" --check; then
  not_ok "apply.sh --check passed even though the pinned keystore was missing"
elif grep -q "debug.keystore" "${WORK_DIR}/check-without.log"; then
  ok "apply.sh --check reports the missing pinned keystore"
else
  not_ok "apply.sh --check failed for an unrelated reason (see ${WORK_DIR}/check-without.log)"
fi

# These assertions read the workflow's code only: comment lines are stripped first, so prose cannot
# satisfy them. They are regression guards over the YAML text, not proof that the job works - only a CI
# run proves that.
workflow_code="$(sed -e 's/^[[:space:]]*#.*$//' -e 's/[[:space:]#]#.*$//' "${WORKFLOW}")"

if grep -q "keytool -genkey" <<<"${workflow_code}"; then
  not_ok "the build workflow still generates a fresh debug keystore on every run"
else
  ok "the build workflow no longer generates an ephemeral debug keystore"
fi

if grep -qF 'patches/local-patches/apply.sh"' <<<"${workflow_code}"; then
  ok "the build workflow installs the pinned keystore by running apply.sh"
else
  not_ok "the build workflow never runs apply.sh, so the pinned keystore cannot reach the build"
fi

if grep -qE 'python3 .*check_apk_signing_cert\.py' <<<"${workflow_code}"; then
  ok "the build workflow runs the certificate checker as a command"
else
  not_ok "the build workflow does not invoke the certificate checker"
fi

if grep -q "print -quit" <<<"${workflow_code}"; then
  not_ok "the certificate step still inspects only the first APK it finds"
else
  ok "the certificate step inspects every APK the build produced"
fi

# shellcheck disable=SC2016  # matching the literal YAML text, not a shell expansion
if grep -qF '"${apks[@]}"' <<<"${workflow_code}"; then
  ok "the certificate step passes the whole APK list to the checker"
else
  not_ok "the certificate step does not pass the collected APK list to the checker"
fi

if grep -qF "records no fingerprint" <<<"${workflow_code}"; then
  ok "the certificate step rejects a pin file that records no fingerprint"
else
  not_ok "an empty pin file would silently disable the certificate gate"
fi

# shellcheck disable=SC2016  # matching the literal YAML text, not a shell expansion
if grep -qF 'exit "${status}"' <<<"${workflow_code}"; then
  ok "the certificate step fails the job when the checker fails"
else
  not_ok "the certificate step does not propagate the checker's exit status"
fi

if [[ ! -f "${PATCH_DIR}/debug.keystore" ]]; then
  pending "local-patches/debug.keystore is absent - create it once with:"
  printf '         keytool -genkeypair -v -keystore local-patches/debug.keystore -storepass android \\\n'
  printf '           -alias androiddebugkey -keypass android -keyalg RSA -keysize 2048 -validity 10000 \\\n'
  printf '           -dname "CN=Android Debug,O=Android,C=US"\n'
else
  ok "local-patches/debug.keystore is present, so every build shares one signing key"

  # The pin must belong to the keystore that ships with the patch set, or every build fails at signing.
  # Both tools exist on the CI runner, so a missing one is a broken gate rather than something to skip.
  if ! command -v keytool >/dev/null 2>&1 || ! command -v openssl >/dev/null 2>&1; then
    not_ok "keytool and openssl are both needed to prove the pin matches the committed keystore"
  elif [[ ! -f "${PIN_FILE}" ]]; then
    not_ok "${PIN_FILE} is missing, so no build can be shown to carry the pinned certificate"
  else
    certificate_pem="$(keytool -exportcert -rfc -keystore "${PATCH_DIR}/debug.keystore" \
      -storepass android -alias androiddebugkey 2>/dev/null || true)"
    recorded="$(awk '{ sub(/#.*/, ""); gsub(/[[:space:]]/, ""); if (length($0) > 0) { print tolower($0); exit } }' \
      "${PIN_FILE}" || true)"
    certificate_der=""
    der_file="${WORK_DIR}/certificate.der"
    if [[ -n "${certificate_pem}" ]] &&
      printf '%s\n' "${certificate_pem}" | openssl x509 -outform DER >"${der_file}" 2>/dev/null &&
      [[ -s "${der_file}" ]]; then
      if command -v sha256sum >/dev/null 2>&1; then
        certificate_der="$(sha256sum "${der_file}" | awk '{print $1}')"
      else
        certificate_der="$(openssl dgst -sha256 "${der_file}" | awk '{print $NF}')"
      fi
    fi
    if [[ -n "${certificate_der}" && "${certificate_der}" == "${recorded}" ]]; then
      ok "the pinned fingerprint is the committed keystore's certificate"
    else
      not_ok "the pin does not match the committed keystore (keystore ${certificate_der:-none}, pin ${recorded:-none})"
    fi
  fi
fi

printf '\n%d passed, %d failed, %d pending\n' "${PASSED}" "${FAILED}" "${PENDING}"
if (( FAILED > 0 )); then
  exit 1
fi
