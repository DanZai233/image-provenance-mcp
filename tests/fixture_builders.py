"""Build the PNG fixtures used by the tests, at test time, from code.

Nothing binary and nothing personal lives in the repository: both fixtures are
assembled here from scratch with the standard library, so the C2PA reader is
exercised against a structure this file wrote. The signed fixture is signed by
nobody — it carries no certificate chain and its signature bytes are filler. It
exists to prove the *parser* behaves, not to prove anything about the world.
"""

from __future__ import annotations

import hashlib
import struct
import zlib

JUMD_LABEL = 0x02
JUMBF_UUID = bytes.fromhex("63327061000000000000000000000000")  # "c2pa"-ish namespace

# --------------------------------------------------------------------------
# CBOR encoder (RFC 8949, definite lengths only — all a manifest needs)
# --------------------------------------------------------------------------


def _head(major: int, value: int) -> bytes:
    if value < 24:
        return bytes([(major << 5) | value])
    if value < 0x100:
        return bytes([(major << 5) | 24, value])
    if value < 0x10000:
        return bytes([(major << 5) | 25]) + struct.pack(">H", value)
    if value < 0x100000000:
        return bytes([(major << 5) | 26]) + struct.pack(">I", value)
    return bytes([(major << 5) | 27]) + struct.pack(">Q", value)


def cbor_encode(obj) -> bytes:
    if obj is None:
        return b"\xf6"
    if obj is True:
        return b"\xf5"
    if obj is False:
        return b"\xf4"
    if isinstance(obj, int):
        return _head(0, obj) if obj >= 0 else _head(1, -obj - 1)
    if isinstance(obj, bytes):
        return _head(2, len(obj)) + obj
    if isinstance(obj, str):
        raw = obj.encode("utf-8")
        return _head(3, len(raw)) + raw
    if isinstance(obj, (list, tuple)):
        return _head(4, len(obj)) + b"".join(cbor_encode(x) for x in obj)
    if isinstance(obj, dict):
        out = [_head(5, len(obj))]
        for k, v in obj.items():
            out.append(cbor_encode(k))
            out.append(cbor_encode(v))
        return b"".join(out)
    raise TypeError(f"cannot CBOR-encode {type(obj).__name__}")


# --------------------------------------------------------------------------
# JUMBF boxes
# --------------------------------------------------------------------------


def box(type_: bytes, payload: bytes) -> bytes:
    return struct.pack(">I", 8 + len(payload)) + type_ + payload


def jumd(label: str) -> bytes:
    return box(b"jumd", JUMBF_UUID + bytes([JUMD_LABEL]) + label.encode("utf-8") + b"\x00")


def jumb(label: str, child_boxes: list[bytes]) -> bytes:
    """A superbox: jumd label followed by content boxes."""
    return box(b"jumb", jumd(label) + b"".join(child_boxes))


def cbor_box(obj) -> bytes:
    return box(b"cbor", cbor_encode(obj))


# --------------------------------------------------------------------------
# PNG assembly
# --------------------------------------------------------------------------


def _chunk(type_: bytes, data: bytes) -> bytes:
    crc = zlib.crc32(type_ + data) & 0xFFFFFFFF
    return struct.pack(">I", len(data)) + type_ + data + struct.pack(">I", crc)


def _raw_rgb(width: int, height: int) -> bytes:
    """A deterministic gradient: no randomness, no external assets."""
    rows = []
    for y in range(height):
        row = bytearray([0])  # filter type 0
        for x in range(width):
            row += bytes(((x * 4) % 256, (y * 6) % 256, ((x + y) * 3) % 256))
        rows.append(bytes(row))
    return b"".join(rows)


def png_bytes(width: int = 96, height: int = 64, extra_chunks: list[bytes] | None = None) -> bytes:
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)  # 8-bit RGB
    body = [_chunk(b"IHDR", ihdr)]
    body.extend(extra_chunks or [])
    body.append(_chunk(b"IDAT", zlib.compress(_raw_rgb(width, height), 9)))
    body.append(_chunk(b"IEND", b""))
    return b"\x89PNG\r\n\x1a\n" + b"".join(body)


def _manifest(claim: dict, actions: dict, digest: bytes) -> bytes:
    return jumb(
        "c2pa",
        [
            jumb("c2pa.claim", [cbor_box(claim)]),
            jumb("c2pa.actions", [cbor_box(actions)]),
            jumb(
                "c2pa.hash.data",
                [cbor_box({"alg": "sha256", "hash": digest, "pad": b"\x00" * 4})],
            ),
            jumb("c2pa.signature", [cbor_box([b"\xa1\x01\x26", {}, b"", b"\x00" * 64])]),
        ],
    )


CLAIM = {
    "claim_generator": "Synthetic Media Service (test fixture)",
    "claim_generator_info": [
        {"name": "Synthetic Media Service (test fixture)", "version": "0.0.0", "specVersion": "2.2.0"}
    ],
    "dc:title": "synthetic.png",
    "instanceID": "urn:c2pa:00000000-0000-0000-0000-000000000000",
}

ACTIONS = {
    "actions": [
        {
            "action": "c2pa.created",
            "when": "2026-01-01T00:00:00Z",
            "softwareAgent": {"name": "Test Bench", "version": "1.0"},
            "digitalSourceType": "http://cv.iptc.org/newscodes/digitalsourcetype/trainedAlgorithmicMedia",
        }
    ]
}


def signed_png_bytes(width: int = 96, height: int = 64) -> bytes:
    """Build a PNG whose caBX chunk holds a manifest bound to the pixel bytes."""
    # The digest covers every byte outside the caBX chunk, so its value cannot
    # depend on the manifest itself. Build once with an empty manifest to learn
    # the exact byte layout, then rebuild with the real one.
    stub = _manifest(CLAIM, ACTIONS, b"\x00" * 32)
    stub_box = _chunk(b"caBX", stub)
    probe = png_bytes(width, height, [stub_box])
    start = 8 + 25  # signature + IHDR chunk
    digest = hashlib.sha256(probe[:start] + probe[start + len(stub_box):]).digest()

    real = _manifest(CLAIM, ACTIONS, digest)
    if len(real) != len(stub):  # both use a 32-byte digest; keep the guard anyway
        raise AssertionError("manifest size drifted, offsets would move")
    return png_bytes(width, height, [_chunk(b"caBX", real)])


def plain_png_bytes(width: int = 96, height: int = 64) -> bytes:
    return png_bytes(width, height)


def write_fixtures(directory) -> dict:
    """Write both fixtures into `directory` and return {name: path}."""
    import os

    os.makedirs(directory, exist_ok=True)
    out = {
        "signed": os.path.join(directory, "signed_synthetic.png"),
        "plain": os.path.join(directory, "plain.png"),
    }
    with open(out["signed"], "wb") as fh:
        fh.write(signed_png_bytes())
    with open(out["plain"], "wb") as fh:
        fh.write(plain_png_bytes())
    return out
