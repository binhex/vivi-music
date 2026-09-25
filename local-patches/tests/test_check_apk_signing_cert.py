"""Tests for the APK signing-certificate fingerprint reader.

The fixtures build a minimal but structurally valid APK Signing Block, so the parser is exercised
against the documented layout without needing the Android SDK.
"""

from __future__ import annotations

import hashlib
import pathlib
import runpy
import struct
import sys

import pytest
from check_apk_signing_cert import ApkFormatError, certificate_fingerprints, main

V2_BLOCK_ID = 0x7109871A
V3_BLOCK_ID = 0xF05368C0
V31_BLOCK_ID = 0x1B93AD61
BLOCK_MAGIC = b"APK Sig Block 42"
EOCD_MAGIC = b"\x50\x4b\x05\x06"

FAKE_CERTIFICATE_A = b"\x30\x82\x01\x0a" + b"A" * 40
FAKE_CERTIFICATE_B = b"\x30\x82\x01\x0a" + b"B" * 40


def _length_prefixed(payload: bytes) -> bytes:
    return struct.pack("<I", len(payload)) + payload


def _v2_value(certificate: bytes) -> bytes:
    """Build one signer whose signed data carries `certificate`."""
    digests = _length_prefixed(
        b""
    )  # no digest entries; the parser only needs to skip this field
    certificates = _length_prefixed(_length_prefixed(certificate))
    attributes = _length_prefixed(b"")
    signed_data = _length_prefixed(digests) + certificates + attributes
    signer = (
        _length_prefixed(signed_data) + _length_prefixed(b"") + _length_prefixed(b"key")
    )
    return _length_prefixed(signer)


def _signing_block(block_id: int, value: bytes) -> bytes:
    pair = struct.pack("<Q", len(value) + 4) + struct.pack("<I", block_id) + value
    # Both size fields count everything after them: the trailing size field and the 16-byte magic.
    size = struct.pack("<Q", len(pair) + 24)
    return size + pair + size + BLOCK_MAGIC


def _apk(path, certificate: bytes, block_id: int = V2_BLOCK_ID) -> str:
    prefix = b"pretend zip contents"
    block = _signing_block(block_id, _v2_value(certificate))
    central_directory = b"\x50\x4b\x01\x02" + b"central directory placeholder"
    cd_offset = struct.pack("<I", len(prefix) + len(block))
    eocd = EOCD_MAGIC + b"\x00" * 12 + cd_offset + b"\x00" * 2
    path.write_bytes(prefix + block + central_directory + eocd)
    return str(path)


def _apk_raw(path, block: bytes) -> str:
    """Write an APK whose signing block is given verbatim, so malformed blocks can be tested."""
    prefix = b"pretend zip contents"
    central_directory = b"\x50\x4b\x01\x02" + b"central directory placeholder"
    cd_offset = struct.pack("<I", len(prefix) + len(block))
    eocd = EOCD_MAGIC + b"\x00" * 12 + cd_offset + b"\x00" * 2
    path.write_bytes(prefix + block + central_directory + eocd)
    return str(path)


def _signing_block_raw(pairs: bytes) -> bytes:
    """Wrap verbatim pair bytes in a block whose declared size is self-consistent."""
    size = struct.pack("<Q", len(pairs) + 24)
    return size + pairs + size + BLOCK_MAGIC


def _v2_value_with_chain(certificates: list[bytes]) -> bytes:
    """Build one signer whose certificate list is a chain: the signer's certificate comes first."""
    digests = _length_prefixed(b"")
    certificate_list = b"".join(
        _length_prefixed(certificate) for certificate in certificates
    )
    attributes = _length_prefixed(b"")
    signed_data = (
        _length_prefixed(digests) + _length_prefixed(certificate_list) + attributes
    )
    signer = (
        _length_prefixed(signed_data) + _length_prefixed(b"") + _length_prefixed(b"key")
    )
    return _length_prefixed(signer)


def _v3_value(certificate: bytes) -> bytes:
    """Build one signer in the v3 shape, including the signer-level SDK range v3 carries."""
    digests = _length_prefixed(b"")
    certificates = _length_prefixed(_length_prefixed(certificate))
    min_sdk = struct.pack("<I", 24)
    max_sdk = struct.pack("<I", 0x7FFFFFFF)
    attributes = _length_prefixed(b"")
    signed_data = (
        _length_prefixed(digests) + certificates + min_sdk + max_sdk + attributes
    )
    signer = (
        _length_prefixed(signed_data)
        + min_sdk
        + max_sdk
        + _length_prefixed(b"")
        + _length_prefixed(b"key")
    )
    return _length_prefixed(signer)


def _apk_v3(path, certificate: bytes) -> str:
    """Write a v3-signed APK whose signed data carries the v3-only SDK range."""
    return _apk_raw(path, _signing_block(V3_BLOCK_ID, _v3_value(certificate)))


def _write_with_zip_comment(path, comment: bytes) -> str:
    """Append a zip comment to a built APK, keeping the end record's comment length consistent."""
    apk = pathlib.Path(path)
    raw = apk.read_bytes()
    eocd = raw.rfind(EOCD_MAGIC)
    apk.write_bytes(raw[: eocd + 20] + struct.pack("<H", len(comment)) + comment)
    return str(apk)


def _multi_pair_block(pairs: list[tuple[int, bytes]]) -> bytes:
    """Build a signing block carrying several id/value pairs, as a v2+v3 signed APK does."""
    encoded = b"".join(
        struct.pack("<Q", len(value) + 4) + struct.pack("<I", block_id) + value
        for block_id, value in pairs
    )
    return _signing_block_raw(encoded)


def test_reports_the_certificate_fingerprint(tmp_path):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)

    assert certificate_fingerprints(apk) == [
        hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    ]


def test_reports_the_fingerprint_of_a_v3_block(tmp_path):
    apk = _apk_v3(tmp_path / "app.apk", FAKE_CERTIFICATE_A)

    assert certificate_fingerprints(apk) == [
        hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    ]


def test_cli_succeeds_when_two_apks_share_a_certificate(tmp_path, capsys):
    first = _apk(tmp_path / "first.apk", FAKE_CERTIFICATE_A)
    second = _apk(tmp_path / "second.apk", FAKE_CERTIFICATE_A)

    assert main([first, second]) == 0
    assert "MISMATCH" not in capsys.readouterr().out


def test_cli_fails_when_two_apks_differ(tmp_path, capsys):
    first = _apk(tmp_path / "first.apk", FAKE_CERTIFICATE_A)
    second = _apk(tmp_path / "second.apk", FAKE_CERTIFICATE_B)

    assert main([first, second]) == 1
    assert "MISMATCH" in capsys.readouterr().out


def test_cli_accepts_a_matching_expectation(tmp_path):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    expected = hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()

    assert main([apk, "--expect", expected]) == 0
    assert main([apk, "--expect", hashlib.sha256(FAKE_CERTIFICATE_B).hexdigest()]) == 1


def test_rejects_a_truncated_signer(tmp_path):
    value = _length_prefixed(b"ab")
    apk = _apk_raw(tmp_path / "app.apk", _signing_block(V2_BLOCK_ID, value))

    with pytest.raises(ApkFormatError, match="truncated signer"):
        certificate_fingerprints(apk)


def test_cli_reports_a_matching_expect_file_silently(tmp_path, capsys):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    expect_file = tmp_path / "signing-cert.sha256"
    expect_file.write_text(
        f"# pinned 2026-09-25\n{hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()}\n"
    )

    assert main([apk, "--expect-file", str(expect_file)]) == 0
    output = capsys.readouterr().out
    assert "MISMATCH" not in output
    assert "NOTICE" not in output


def test_cli_fails_against_a_stale_expect_file(tmp_path, capsys):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    expect_file = tmp_path / "signing-cert.sha256"
    expect_file.write_text(hashlib.sha256(FAKE_CERTIFICATE_B).hexdigest() + "\n")

    assert main([apk, "--expect-file", str(expect_file)]) == 1
    assert "MISMATCH" in capsys.readouterr().out


def test_cli_notes_an_unrecorded_expect_file(tmp_path, capsys):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)

    assert main([apk, "--expect-file", str(tmp_path / "absent.sha256")]) == 0
    assert "NOTICE" in capsys.readouterr().out


def test_rejects_a_file_without_a_zip_end_record(tmp_path):
    path = tmp_path / "app.apk"
    path.write_bytes(b"not a zip file")

    with pytest.raises(ApkFormatError, match="end-of-central-directory"):
        certificate_fingerprints(str(path))


def test_rejects_an_out_of_range_central_directory(tmp_path):
    path = tmp_path / "app.apk"
    path.write_bytes(EOCD_MAGIC + b"\x00" * 12 + struct.pack("<I", 5) + b"\x00" * 2)

    with pytest.raises(ApkFormatError, match="central directory offset"):
        certificate_fingerprints(str(path))


def test_rejects_a_file_without_the_signing_block_magic(tmp_path):
    body = b"x" * 64
    path = tmp_path / "app.apk"
    path.write_bytes(
        body + EOCD_MAGIC + b"\x00" * 12 + struct.pack("<I", len(body)) + b"\x00" * 2
    )

    with pytest.raises(ApkFormatError, match="no APK Signing Block"):
        certificate_fingerprints(str(path))


def test_rejects_an_out_of_range_block_size(tmp_path):
    block = struct.pack("<Q", 0) + struct.pack("<Q", 0) + BLOCK_MAGIC
    apk = _apk_raw(tmp_path / "app.apk", block)

    with pytest.raises(ApkFormatError, match="size is out of range"):
        certificate_fingerprints(apk)


def test_rejects_a_malformed_block_entry(tmp_path):
    pairs = struct.pack("<Q", 0) + struct.pack("<I", V2_BLOCK_ID)
    apk = _apk_raw(tmp_path / "app.apk", _signing_block_raw(pairs))

    with pytest.raises(ApkFormatError, match="malformed APK Signing Block entry"):
        certificate_fingerprints(apk)


def test_rejects_a_truncated_length_prefix(tmp_path):
    apk = _apk_raw(tmp_path / "app.apk", _signing_block(V2_BLOCK_ID, b"\x00\x00"))

    with pytest.raises(ApkFormatError, match="truncated length prefix"):
        certificate_fingerprints(apk)


def test_rejects_a_truncated_length_prefixed_value(tmp_path):
    value = struct.pack("<I", 999) + b"ab"
    apk = _apk_raw(tmp_path / "app.apk", _signing_block(V2_BLOCK_ID, value))

    with pytest.raises(ApkFormatError, match="truncated length-prefixed value"):
        certificate_fingerprints(apk)


def test_rejects_a_block_without_a_v2_or_v3_certificate(tmp_path):
    apk = _apk_raw(tmp_path / "app.apk", _signing_block(0x42726577, b"\x00" * 8))

    with pytest.raises(
        ApkFormatError, match="no APK Signature Scheme v2 or v3 certificate"
    ):
        certificate_fingerprints(apk)


def test_cli_reports_an_unreadable_expect_file(tmp_path, capsys):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)

    assert main([apk, "--expect-file", str(tmp_path)]) == 1
    assert "ERROR: cannot read" in capsys.readouterr().out


def test_cli_notes_an_expect_file_without_a_fingerprint(tmp_path, capsys):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    expect_file = tmp_path / "empty.sha256"
    expect_file.write_text("# nothing recorded yet\n\n")

    assert main([apk, "--expect-file", str(expect_file)]) == 0
    assert "NOTICE" in capsys.readouterr().out


def test_cli_fails_when_an_apk_cannot_be_read(tmp_path, capsys):
    assert main([str(tmp_path / "missing.apk")]) == 1
    assert "ERROR" in capsys.readouterr().out


def test_rejects_a_truncated_end_of_central_directory(tmp_path):
    path = tmp_path / "app.apk"
    path.write_bytes(EOCD_MAGIC + b"\x00" * 4)

    with pytest.raises(ApkFormatError, match="end-of-central-directory"):
        certificate_fingerprints(str(path))


def test_rejects_an_end_record_with_a_bogus_comment_length(tmp_path):
    body = b"x" * 64
    path = tmp_path / "app.apk"
    path.write_bytes(
        body
        + EOCD_MAGIC
        + b"\x00" * 12
        + struct.pack("<I", len(body))
        + struct.pack("<H", 5)
    )

    with pytest.raises(ApkFormatError, match="end-of-central-directory"):
        certificate_fingerprints(str(path))


def test_rejects_a_signer_declaring_more_signed_data_than_it_carries(tmp_path):
    signer = struct.pack("<I", 999) + _length_prefixed(b"")
    block = _signing_block(V2_BLOCK_ID, _length_prefixed(signer))
    apk = _apk_raw(tmp_path / "app.apk", block)

    with pytest.raises(ApkFormatError, match="declares"):
        certificate_fingerprints(apk)


def test_cli_accepts_an_uppercase_expectation(tmp_path):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    expected = hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()

    assert main([apk, "--expect", expected.upper()]) == 0


def test_cli_accepts_a_colon_separated_expectation(tmp_path):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    fingerprint = hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    colon_separated = ":".join(
        fingerprint[index : index + 2] for index in range(0, len(fingerprint), 2)
    )

    assert main([apk, "--expect", colon_separated]) == 0


def test_reports_only_the_signing_certificate_of_a_chain(tmp_path):
    value = _v2_value_with_chain([FAKE_CERTIFICATE_A, FAKE_CERTIFICATE_B])
    apk = _apk_raw(tmp_path / "app.apk", _signing_block(V2_BLOCK_ID, value))

    assert certificate_fingerprints(apk) == [
        hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    ]


def test_parses_an_apk_whose_zip_comment_holds_the_end_record_magic(tmp_path):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    commented = _write_with_zip_comment(apk, EOCD_MAGIC + b" and then some")

    assert certificate_fingerprints(commented) == [
        hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    ]


def test_reports_the_fingerprint_of_a_v3_1_block(tmp_path):
    block = _signing_block(V31_BLOCK_ID, _v3_value(FAKE_CERTIFICATE_A))
    apk = _apk_raw(tmp_path / "app.apk", block)

    assert certificate_fingerprints(apk) == [
        hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    ]


def test_reports_each_fingerprint_once_when_both_blocks_are_present(tmp_path):
    block = _multi_pair_block(
        [
            (V2_BLOCK_ID, _v2_value(FAKE_CERTIFICATE_A)),
            (V3_BLOCK_ID, _v3_value(FAKE_CERTIFICATE_A)),
        ]
    )
    apk = _apk_raw(tmp_path / "app.apk", block)

    assert certificate_fingerprints(apk) == [
        hashlib.sha256(FAKE_CERTIFICATE_A).hexdigest()
    ]


def test_rejects_signed_data_shorter_than_a_length_prefix(tmp_path):
    signer = struct.pack("<I", 2) + b"ab"
    block = _signing_block(V2_BLOCK_ID, _length_prefixed(signer))
    apk = _apk_raw(tmp_path / "app.apk", block)

    with pytest.raises(ApkFormatError, match="certificate list"):
        certificate_fingerprints(apk)


def test_rejects_signed_data_without_room_for_the_certificate_list(tmp_path):
    signed_data = _length_prefixed(b"ab")
    signer = struct.pack("<I", len(signed_data)) + signed_data
    block = _signing_block(V2_BLOCK_ID, _length_prefixed(signer))
    apk = _apk_raw(tmp_path / "app.apk", block)

    with pytest.raises(ApkFormatError, match="digests"):
        certificate_fingerprints(apk)


def test_rejects_a_certificate_list_that_overruns_the_signed_data(tmp_path):
    signed_data = _length_prefixed(b"") + struct.pack("<I", 999) + b"ab"
    signer = struct.pack("<I", len(signed_data)) + signed_data
    block = _signing_block(V2_BLOCK_ID, _length_prefixed(signer))
    apk = _apk_raw(tmp_path / "app.apk", block)

    with pytest.raises(ApkFormatError, match="certificate list"):
        certificate_fingerprints(apk)


def test_module_entry_point_runs_main(tmp_path, monkeypatch):
    apk = _apk(tmp_path / "app.apk", FAKE_CERTIFICATE_A)
    monkeypatch.setattr(sys, "argv", ["check_apk_signing_cert.py", apk])

    with pytest.raises(SystemExit) as exit_info:
        runpy.run_module("check_apk_signing_cert", run_name="__main__")

    assert exit_info.value.code == 0
