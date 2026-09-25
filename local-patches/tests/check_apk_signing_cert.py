#!/usr/bin/env python3
"""Report the signing-certificate fingerprint of an APK's APK Signature Scheme v2/v3 block.

Android only accepts an in-place update when the update is signed with the same certificate as the
installed app, so this fingerprint is the value that must stay identical across builds. Only the
public certificate is read; no private key material is involved.
"""

from __future__ import annotations

import argparse
import hashlib
import struct

V2_BLOCK_ID = 0x7109871A
V3_BLOCK_ID = 0xF05368C0
V31_BLOCK_ID = 0x1B93AD61
BLOCK_MAGIC = b"APK Sig Block 42"
EOCD_MAGIC = b"\x50\x4b\x05\x06"


class ApkFormatError(Exception):
    """Raised when a file does not carry an APK Signature Scheme v2/v3 certificate.

    Also raised when the APK Signing Block itself is malformed.
    """


def _central_directory_offset(data: bytes) -> int:
    """Return the central directory offset of the last consistent end-of-central-directory record."""
    position = len(data)
    while True:
        position = data.rfind(EOCD_MAGIC, 0, position)
        if position < 0:
            raise ApkFormatError("no zip end-of-central-directory record found")
        if position + 22 <= len(data):
            comment_length = struct.unpack_from("<H", data, position + 20)[0]
            if position + 22 + comment_length == len(data):
                return struct.unpack_from("<I", data, position + 16)[0]


def _signing_block(data: bytes) -> bytes:
    """Return the APK Signing Block, which sits immediately before the central directory."""
    central_directory = _central_directory_offset(data)
    if central_directory < 24 or central_directory > len(data):
        raise ApkFormatError("central directory offset is out of range")
    if data[central_directory - 16 : central_directory] != BLOCK_MAGIC:
        raise ApkFormatError("no APK Signing Block before the central directory")
    size = struct.unpack_from("<Q", data, central_directory - 24)[0]
    start = central_directory - (size + 8)
    if size < 24 or start < 0:
        raise ApkFormatError("APK Signing Block size is out of range")
    return data[start:central_directory]


def _block_pairs(block: bytes) -> dict[int, bytes]:
    """Split the signing block into its id/value pairs; entry lengths are uint64, ids uint32."""
    pairs: dict[int, bytes] = {}
    position, end = 8, len(block) - 24
    while position < end:
        entry_length = struct.unpack_from("<Q", block, position)[0]
        if entry_length < 4 or position + 8 + entry_length > end:
            raise ApkFormatError("malformed APK Signing Block entry")
        block_id = struct.unpack_from("<I", block, position + 8)[0]
        pairs[block_id] = block[position + 12 : position + 8 + entry_length]
        position += 8 + entry_length
    return pairs


def _length_prefixed_values(blob: bytes) -> list[bytes]:
    """Split a sequence of uint32-length-prefixed values."""
    values: list[bytes] = []
    position = 0
    while position < len(blob):
        if position + 4 > len(blob):
            raise ApkFormatError("truncated length prefix")
        length = struct.unpack_from("<I", blob, position)[0]
        start = position + 4
        if start + length > len(blob):
            raise ApkFormatError("truncated length-prefixed value")
        values.append(blob[start : start + length])
        position = start + length
    return values


def _signing_certificate(signed_data: bytes) -> bytes | None:
    """Return the signing certificate from signed data, or None when it lists none.

    Both layouts put the certificate list second, but v3 follows it with bare uint32 minSdk and
    maxSdk values, so walking the whole blob would misread those integers as length prefixes.
    """
    if len(signed_data) < 4:
        raise ApkFormatError("signed data is too short to hold a certificate list")
    digests_length = struct.unpack_from("<I", signed_data, 0)[0]
    position = 4 + digests_length
    if position + 4 > len(signed_data):
        raise ApkFormatError("digests length runs past the signed data")
    certificates_length = struct.unpack_from("<I", signed_data, position)[0]
    start = position + 4
    if start + certificates_length > len(signed_data):
        raise ApkFormatError("certificate list runs past the signed data")
    certificate_list = _length_prefixed_values(
        signed_data[start : start + certificates_length]
    )
    return certificate_list[0] if certificate_list else None


def _certificates(block_value: bytes) -> list[bytes]:
    """Pull the signing certificate out of each signer of one signing block."""
    certificates: list[bytes] = []
    for signer in _length_prefixed_values(block_value):
        if len(signer) < 4:
            raise ApkFormatError("truncated signer")
        signed_data_length = struct.unpack_from("<I", signer, 0)[0]
        if signed_data_length > len(signer) - 4:
            raise ApkFormatError("signer declares more signed data than it carries")
        certificate = _signing_certificate(signer[4 : 4 + signed_data_length])
        if certificate:
            # A signer's certificate is the first entry of its chain.
            certificates.append(certificate)
    return certificates


def certificate_fingerprints(path: str) -> list[str]:
    """Return the SHA-256 fingerprint of each distinct signing certificate in the APK at `path`."""
    with open(path, "rb") as handle:
        data = handle.read()

    pairs = _block_pairs(_signing_block(data))
    found: list[bytes] = []
    for block_id in (V2_BLOCK_ID, V3_BLOCK_ID, V31_BLOCK_ID):
        if block_id in pairs:
            found.extend(_certificates(pairs[block_id]))
    if not found:
        raise ApkFormatError("no APK Signature Scheme v2 or v3 certificate found")
    fingerprints: list[str] = []
    for certificate in found:
        fingerprint = hashlib.sha256(certificate).hexdigest()
        if fingerprint not in fingerprints:
            fingerprints.append(fingerprint)
    return fingerprints


def _normalise_fingerprint(value: str | None) -> str | None:
    """Return the fingerprint in the comparable form: lowercase hex without separators."""
    if not value:
        return None
    return value.replace(":", "").replace(" ", "").lower()


def _read_expected(path: str) -> tuple[str | None, int]:
    """Return the expectation recorded in `path` (or None) and the exit code to use.

    The file holds one fingerprint; `#` comments and blank lines are ignored. A NOTICE is printed
    when the file is missing or records nothing, and an ERROR when it cannot be read.
    """
    try:
        with open(path, encoding="utf-8") as handle:
            for line in handle:
                token = line.split("#", 1)[0].strip()
                if token:
                    return _normalise_fingerprint(token), 0
    except FileNotFoundError:
        print(
            f"NOTICE: {path} does not exist yet, so there is nothing to compare against"
        )
        return None, 0
    except OSError as error:
        print(f"ERROR: cannot read {path}: {error}")
        return None, 1
    print(
        f"NOTICE: {path} records no fingerprint, so there is nothing to compare against"
    )
    return None, 0


def _collect_fingerprints(apks: list[str]) -> tuple[dict[str, list[str]], int]:
    """Read every APK, returning the fingerprints per path and a 0 exit code.

    On the first unreadable APK, print an ERROR line and return an empty mapping with exit code 1.
    """
    results: dict[str, list[str]] = {}
    for apk in apks:
        try:
            results[apk] = certificate_fingerprints(apk)
        except (OSError, ApkFormatError) as error:
            print(f"ERROR {apk}: {error}")
            return {}, 1
    return results, 0


def _resolve_expected(args: argparse.Namespace) -> tuple[str | None, int]:
    """Resolve the expected fingerprint from `--expect`, overridden by `--expect-file`.

    Return the resolved fingerprint (or None) and the exit code to use; a non-zero code comes from
    an unreadable `--expect-file`, and an unrecorded one falls back to `--expect`. Fingerprints are
    compared regardless of case and separators.
    """
    if not args.expect_file:
        return _normalise_fingerprint(args.expect), 0
    recorded, code = _read_expected(args.expect_file)
    if code != 0:
        return None, code
    return recorded or _normalise_fingerprint(args.expect), 0


def _report(results: dict[str, list[str]], expected: str | None) -> int:
    """Print every fingerprint, returning 0 only when they agree with each other and `expected`."""
    seen: set[str] = set()
    for apk, fingerprints in results.items():
        for fingerprint in fingerprints:
            print(f"{fingerprint}  {apk}")
            seen.add(fingerprint)

    if len(seen) > 1:
        print("MISMATCH: the listed APKs are signed with different certificates")
        return 1
    if expected and expected not in seen:
        print(f"MISMATCH: expected {expected}, found {', '.join(sorted(seen))}")
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    """Print the fingerprints of the given APKs, failing when they disagree or miss an expectation."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apks", nargs="+", help="APK files to inspect")
    parser.add_argument("--expect", help="fingerprint every APK must carry")
    parser.add_argument(
        "--expect-file", help="file holding the expected fingerprint, if recorded"
    )
    args = parser.parse_args(argv)

    results, code = _collect_fingerprints(args.apks)
    if code != 0:
        return code
    expected, code = _resolve_expected(args)
    if code != 0:
        return code
    return _report(results, expected)


if __name__ == "__main__":
    raise SystemExit(main())
