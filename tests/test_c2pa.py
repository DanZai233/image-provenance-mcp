"""Tier-1 tests: CBOR decoding, carrier parsing, hard binding, verdicts."""

from __future__ import annotations

import pathlib
import shutil
import struct
import tempfile
import unittest

from provenance_mcp import c2pa_core

FIXTURES = pathlib.Path(__file__).parent / "fixtures"
SIGNED = FIXTURES / "signed_chatgpt.png"
PLAIN = FIXTURES / "plain.png"


class TestCBOR(unittest.TestCase):
    def test_integers(self):
        cases = {
            b"\x00": 0,
            b"\x17": 23,
            b"\x18\x18": 24,
            b"\x19\x01\x00": 256,
            b"\x1a\x00\x01\x00\x00": 65536,
        }
        for raw, want in cases.items():
            got, pos = c2pa_core.cbor_decode(raw)
            self.assertEqual(got, want, raw.hex())
            self.assertEqual(pos, len(raw))

    def test_negative_and_simple(self):
        self.assertEqual(c2pa_core.cbor_decode(b"\x20")[0], -1)
        self.assertEqual(c2pa_core.cbor_decode(b"\x38\x63")[0], -100)
        self.assertIs(c2pa_core.cbor_decode(b"\xf5")[0], True)
        self.assertIsNone(c2pa_core.cbor_decode(b"\xf6")[0])

    def test_text_bytes_container(self):
        self.assertEqual(c2pa_core.cbor_decode(b"\x63abc")[0], "abc")
        self.assertEqual(c2pa_core.cbor_decode(b"\x43ab\x00")[0], b"ab\x00")
        self.assertEqual(c2pa_core.cbor_decode(b"\x82\x01\x02")[0], [1, 2])
        self.assertEqual(c2pa_core.cbor_decode(b"\xa1\x61a\x01")[0], {"a": 1})

    def test_indefinite(self):
        self.assertEqual(c2pa_core.cbor_decode(b"\x9f\x01\x02\xff")[0], [1, 2])

    def test_tag_is_transparent(self):
        # tag 18 (COSE_Sign1) wraps an array
        self.assertEqual(c2pa_core.cbor_decode(b"\xd2\x81\x01")[0], [1])


class TestSignedImage(unittest.TestCase):
    def setUp(self):
        self.rep = c2pa_core.analyse(str(SIGNED))

    def test_carrier_found(self):
        self.assertEqual(self.rep["carrier"], "png:caBX")
        self.assertTrue(self.rep["has_manifest"])

    def test_verdict_is_ai(self):
        self.assertEqual(self.rep["verdict"], "AI_GENERATED")
        self.assertIn("trainedAlgorithmicMedia", self.rep["verdict_reason"])

    def test_actions_decoded(self):
        names = [a["action"] for a in self.rep["actions"]]
        self.assertTrue(any("created" in (n or "") for n in names), names)
        created = next(a for a in self.rep["actions"] if "created" in (a["action"] or ""))
        self.assertEqual(created["agent"], "ChatGPT")

    def test_claim_generator(self):
        self.assertEqual(self.rep["claim_generator"], "OpenAI Media Service API")
        self.assertEqual(self.rep["claim_generator_info"]["specVersion"], "2.2.0")

    def test_hash_verified(self):
        self.assertEqual(self.rep["hash"]["ok"], True)
        self.assertEqual(len(self.rep["hash"]["stored"]), 64)

    def test_cert_chain(self):
        certs = self.rep["certificates"]
        self.assertTrue(certs)
        self.assertIn("OpenAI", certs[0]["subject"])


class TestTamper(unittest.TestCase):
    """Flip one byte inside IDAT while keeping the manifest: the binding must fail."""

    def test_flip_byte_breaks_binding(self):
        data = bytearray(SIGNED.read_bytes())
        pos = 8
        flipped = False
        while pos < len(data):
            (length,) = struct.unpack(">I", data[pos:pos + 4])
            ctype = bytes(data[pos + 4:pos + 8])
            if ctype == b"IDAT":
                data[pos + 8 + 5000] ^= 0x01
                flipped = True
                break
            pos += 12 + length
        self.assertTrue(flipped, "no IDAT chunk found")

        with tempfile.TemporaryDirectory() as tmp:
            victim = pathlib.Path(tmp) / "tampered.png"
            victim.write_bytes(data)
            rep = c2pa_core.analyse(str(victim))

        self.assertEqual(rep["verdict"], "INVALID_HASH")
        self.assertEqual(rep["hash"]["ok"], False)
        # both strategies agree, which is what makes the mismatch trustworthy
        tried = rep["hash"]["tried"]
        self.assertEqual(len(tried), 2)
        self.assertEqual(len({t["computed"] for t in tried}), 1)


class TestNoManifest(unittest.TestCase):
    def test_plain_png(self):
        rep = c2pa_core.analyse(str(PLAIN))
        self.assertFalse(rep["has_manifest"])
        self.assertEqual(rep["verdict"], "NO_C2PA")

    def test_truncated_file_does_not_raise(self):
        with tempfile.TemporaryDirectory() as tmp:
            victim = pathlib.Path(tmp) / "trunc.png"
            victim.write_bytes(SIGNED.read_bytes()[:400])
            rep = c2pa_core.analyse(str(victim))
        self.assertFalse(rep["has_manifest"])

    def test_missing_file_raises_filenotfound(self):
        with self.assertRaises(FileNotFoundError):
            c2pa_core.analyse("/nonexistent/nope.png")


if __name__ == "__main__":
    unittest.main()
