"""Tests fuer den RAM-Pruefer des Widescreen-Codes (synthetische Manifeste)."""

from __future__ import annotations

import struct
import sys
import unittest
from pathlib import Path

_TOOLS = Path(__file__).resolve().parent.parent / "tools"
sys.path.insert(0, str(_TOOLS / "widescreen"))
sys.path.insert(0, str(_TOOLS / "common"))

import bake as baker  # noqa: E402
import dol as dolfile  # noqa: E402
import gecko  # noqa: E402
import verify_ram  # noqa: E402

INI = """[Gecko]
$Test [autor]
04003104 AABBCCDD
C2003108 00000002
3B20FFA9 93380004
931F0140 00000000
"""
CAVE = 0x80600000


def baked_manifest(code, cave, tamper=None):
    placements = baker.layout(code, cave)
    reads = {}
    for i, w in enumerate(code.writes):
        reads[f"write-{i}"] = {"u32": hex(w.value)}
    for i, inj in enumerate(code.injections):
        reads[f"site-{i}"] = {"u32": hex(dolfile.branch(inj.address, placements[i].address))}
    words = [w for p in placements for w in p.words]
    reads["cave"] = {"hex": b"".join(struct.pack(">I", w) for w in words).hex()}
    if tamper:
        tamper(reads)
    return {"reads": reads}


class ReadsTests(unittest.TestCase):
    def test_lists_writes_sites_and_cave(self):
        code = gecko.parse(INI, "Test")
        out = verify_ram.reads(code, CAVE)
        self.assertEqual(len(out), 3)
        self.assertTrue(out[-1].startswith(f"0x{CAVE:08X}:16:cave"))

    def test_gecko_variant_reads_the_handler_window_instead_of_a_cave(self):
        code = gecko.parse(INI, "Test")
        out = verify_ram.reads(code, None)
        self.assertEqual(len(out), 3)
        self.assertTrue(out[-1].endswith(":handler"))
        self.assertFalse(any(r.endswith(":cave") for r in out))


class CheckTests(unittest.TestCase):
    def setUp(self):
        self.code = gecko.parse(INI, "Test")

    def test_accepts_a_consistent_baked_ram(self):
        self.assertEqual(verify_ram.check(self.code, baked_manifest(self.code, CAVE), CAVE, {}), [])

    def test_reports_a_wrong_write(self):
        m = baked_manifest(self.code, CAVE, lambda r: r.update({"write-0": {"u32": "0x0"}}))
        self.assertEqual(len(verify_ram.check(self.code, m, CAVE, {})), 1)

    def test_reports_a_site_without_branch(self):
        m = baked_manifest(self.code, CAVE, lambda r: r.update({"site-0": {"u32": "0x60000000"}}))
        self.assertIn("kein Sprung", verify_ram.check(self.code, m, CAVE, {})[0])

    def test_reports_a_branch_to_the_wrong_place(self):
        wrong = dolfile.branch(0x80003108, CAVE + 0x100)
        m = baked_manifest(self.code, CAVE, lambda r: r.update({"site-0": {"u32": hex(wrong)}}))
        self.assertIn("springt nach", verify_ram.check(self.code, m, CAVE, {})[0])

    def test_reports_a_corrupted_cave(self):
        def tamper(r):
            data = bytearray(bytes.fromhex(r["cave"]["hex"]))
            data[0] ^= 0xFF
            r["cave"]["hex"] = data.hex()
        m = baked_manifest(self.code, CAVE, tamper)
        self.assertIn("Codebereich", verify_ram.check(self.code, m, CAVE, {})[0])

    def test_gecko_variant_compares_the_body_read_from_the_handler(self):
        body = b"".join(struct.pack(">I", w) for w in self.code.injections[0].body)
        m = {"reads": {"write-0": {"u32": "0xAABBCCDD"},
                       "site-0": {"u32": hex(dolfile.branch(0x80003108, 0x80001800))}}}
        self.assertEqual(verify_ram.check(self.code, m, None, {"body-0": body}), [])
        self.assertEqual(len(verify_ram.check(self.code, m, None, {"body-0": b"\0" * 12})), 1)


if __name__ == "__main__":
    unittest.main()
