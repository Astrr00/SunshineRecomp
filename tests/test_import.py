"""Tests fuer den Disc-Import.

Es wird ein synthetisches Abbild im GameCube-Format erzeugt. Damit ist die
Formatlogik pruefbar, ohne Spieldaten zu benoetigen oder zu verteilen. Ein
echtes Abbild ist damit ausdruecklich nicht getestet.
"""

from __future__ import annotations

import hashlib
import struct
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "tools" / "import"))

import gcm  # noqa: E402
import importer  # noqa: E402

# Die Offsets liegen bewusst hinter den festen Systembereichen der Disc
# (boot.bin 0x0-0x440, bi2.bin 0x440-0x2440, Apploader ab 0x2440).
DOL_OFFSET = 0x3000
DOL_LENGTH = 0x140
FST_OFFSET = 0x4000
DATA_OFFSET = 0x5000
APPLOADER_PAYLOAD = 0x80
APPLOADER_TRAILER = 0x10
APPLOADER_LENGTH = 0x20 + APPLOADER_PAYLOAD + APPLOADER_TRAILER

MAP_CONTENT = b"80003100 000030 80003100  0 memset\n"
FILE_CONTENT = b"payload"


def build_image(game_code: bytes = b"GMSE", maker: bytes = b"01",
                version: int = 0, include_map: bool = True) -> bytes:
    """Baut ein minimales, formal gueltiges GameCube-Abbild."""
    names: list[bytes] = []

    def add_name(name: bytes) -> int:
        offset = sum(len(n) + 1 for n in names)
        names.append(name)
        return offset

    map_name = add_name(b"mario.MAP") if include_map else 0
    dir_name = add_name(b"data")
    inner_name = add_name(b"inside.bin")

    entries: list[bytes] = []

    def entry(is_dir: bool, name_offset: int, arg1: int, arg2: int) -> bytes:
        return struct.pack(">III", (int(is_dir) << 24) | name_offset, arg1, arg2)

    map_offset = DATA_OFFSET
    inner_offset = DATA_OFFSET + 0x100

    # Wurzel: arg2 ist die Gesamtzahl der Eintraege.
    count = 4 if include_map else 3
    entries.append(entry(True, 0, 0, count))
    if include_map:
        entries.append(entry(False, map_name, map_offset, len(MAP_CONTENT)))
    # Verzeichnis "data": arg2 ist der Index hinter dem letzten Kindeintrag.
    entries.append(entry(True, dir_name, 0, count))
    entries.append(entry(False, inner_name, inner_offset, len(FILE_CONTENT)))

    string_table = b"".join(n + b"\0" for n in names)
    fst = b"".join(entries) + string_table

    image = bytearray(DATA_OFFSET + 0x200)
    image[0x00:0x04] = game_code
    image[0x04:0x06] = maker
    image[0x06] = 0
    image[0x07] = version
    struct.pack_into(">I", image, gcm.DISC_MAGIC_OFFSET, gcm.DISC_MAGIC)
    image[0x20:0x20 + 22] = b"SUPER MARIO SUNSHINE\0\0"
    struct.pack_into(">I", image, gcm.OFF_DOL, DOL_OFFSET)
    struct.pack_into(">I", image, gcm.OFF_FST, FST_OFFSET)
    struct.pack_into(">I", image, gcm.OFF_FST_SIZE, len(fst))

    # Apploader-Kopf: Nutzlast- und Anhangslaenge stehen getrennt.
    struct.pack_into(">I", image, gcm.APPLOADER_OFFSET + 0x14, APPLOADER_PAYLOAD)
    struct.pack_into(">I", image, gcm.APPLOADER_OFFSET + 0x18, APPLOADER_TRAILER)

    # DOL-Kopf: ein Textsegment, damit sich die Laenge bestimmen laesst.
    struct.pack_into(">I", image, DOL_OFFSET + 0x00, 0x100)
    struct.pack_into(">I", image, DOL_OFFSET + 0x90, 0x40)

    image[FST_OFFSET:FST_OFFSET + len(fst)] = fst
    if include_map:
        image[map_offset:map_offset + len(MAP_CONTENT)] = MAP_CONTENT
    image[inner_offset:inner_offset + len(FILE_CONTENT)] = FILE_CONTENT
    return bytes(image)


def write_image(directory: Path, **kwargs) -> Path:
    path = directory / "disc.iso"
    path.write_bytes(build_image(**kwargs))
    return path


def register_synthetic(image: Path, game_id: str = "GMSE01", version: int = 0,
                       ships_symbol_map: bool = False):
    """Traegt das synthetische Abbild als erwartete Revision ein."""
    data = image.read_bytes()
    revision = importer.Revision(
        game_id=game_id,
        version=version,
        label="Synthetisches Testabbild",
        size=len(data),
        sha256=hashlib.sha256(data).hexdigest(),
        verified=False,
        ships_symbol_map=ships_symbol_map,
    )
    return {f"{game_id}/{version}": revision}


class HeaderTests(unittest.TestCase):
    def test_reads_identity_and_offsets(self):
        with TemporaryDirectory() as tmp:
            image = write_image(Path(tmp))
            with image.open("rb") as stream:
                header = gcm.read_header(stream)
        self.assertEqual(header.game_id, "GMSE01")
        self.assertEqual(header.version, 0)
        self.assertEqual(header.revision, "GMSE01 Rev 0")
        self.assertEqual(header.game_name, "SUPER MARIO SUNSHINE")
        self.assertEqual(header.dol_offset, DOL_OFFSET)

    def test_rejects_non_gamecube_file(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "not-a-disc.iso"
            path.write_bytes(b"\0" * gcm.HEADER_SIZE)
            with path.open("rb") as stream:
                with self.assertRaises(gcm.DiscError) as caught:
                    gcm.read_header(stream)
        self.assertIn("Magic-Signatur", str(caught.exception))

    def test_names_compressed_container_formats(self):
        with TemporaryDirectory() as tmp:
            path = Path(tmp) / "compressed.rvz"
            path.write_bytes(b"RVZ\x01" + b"\0" * 64)
            with path.open("rb") as stream:
                with self.assertRaises(gcm.DiscError) as caught:
                    gcm.read_header(stream)
        self.assertIn("RVZ", str(caught.exception))


class FstTests(unittest.TestCase):
    def test_lists_files_with_directory_prefix(self):
        with TemporaryDirectory() as tmp:
            image = write_image(Path(tmp))
            with image.open("rb") as stream:
                header = gcm.read_header(stream)
                files = gcm.read_fst(stream, header)
        paths = {f.path: f for f in files}
        self.assertIn("mario.MAP", paths)
        self.assertIn("data/inside.bin", paths)
        self.assertEqual(paths["mario.MAP"].size, len(MAP_CONTENT))

    def test_dol_length_from_segment_table(self):
        with TemporaryDirectory() as tmp:
            image = write_image(Path(tmp))
            with image.open("rb") as stream:
                self.assertEqual(gcm.dol_size(stream, DOL_OFFSET), DOL_LENGTH)


class ImportTests(unittest.TestCase):
    def setUp(self):
        self._saved = dict(importer.SUPPORTED_REVISIONS)

    def tearDown(self):
        importer.SUPPORTED_REVISIONS.clear()
        importer.SUPPORTED_REVISIONS.update(self._saved)

    def test_accepts_matching_copy_and_extracts(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(register_synthetic(image))

            report = importer.run(image, root / "out")

        self.assertTrue(report.checksum_matches)
        self.assertTrue(report.symbol_map_found)
        self.assertEqual(report.extracted_files, 2)

    def test_extracted_layout_and_receipt(self):
        """Das Ergebnis muss Dolphins Anordnung entsprechen (sys/ und files/)."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(register_synthetic(image))
            out = root / "out"
            importer.run(image, out)

            self.assertEqual((out / "files" / "mario.MAP").read_bytes(), MAP_CONTENT)
            self.assertEqual((out / "files" / "data" / "inside.bin").read_bytes(),
                             FILE_CONTENT)
            self.assertTrue((out / "import.json").is_file())

    def test_system_area_sizes(self):
        """Die Systembereiche liegen fest; ihre Laengen sind pruefbar."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(register_synthetic(image))
            out = root / "out"
            importer.run(image, out)

            system = out / "sys"
            self.assertEqual((system / "boot.bin").stat().st_size, gcm.BOOT_BIN_SIZE)
            self.assertEqual((system / "bi2.bin").stat().st_size, gcm.BI2_SIZE)
            self.assertEqual((system / "apploader.img").stat().st_size,
                             APPLOADER_LENGTH)
            self.assertEqual((system / "main.dol").stat().st_size, DOL_LENGTH)
            self.assertTrue((system / "fst.bin").stat().st_size > 0)

    def test_rejects_modified_copy(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(register_synthetic(image))
            # Ein Byte ausserhalb des Headers veraendern.
            data = bytearray(image.read_bytes())
            data[DATA_OFFSET + 0x100] ^= 0xFF
            image.write_bytes(bytes(data))

            with self.assertRaises(importer.ImportError_) as caught:
                importer.run(image, root / "out")
        self.assertIn("Integritaetspruefung", str(caught.exception))

    def test_mismatch_can_be_forced(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(register_synthetic(image))
            data = bytearray(image.read_bytes())
            data[DATA_OFFSET + 0x100] ^= 0xFF
            image.write_bytes(bytes(data))

            report = importer.run(image, root / "out", allow_mismatch=True)
        self.assertFalse(report.checksum_matches)
        self.assertTrue(report.warnings)

    def test_explains_wrong_region(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root, game_code=b"GMSJ")
            with self.assertRaises(importer.ImportError_) as caught:
                importer.analyse(image)
        message = str(caught.exception)
        self.assertIn("Japan", message)
        self.assertIn("GMSJ01", message)

    def test_explains_wrong_game(self):
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root, game_code=b"GALE")
            with self.assertRaises(importer.ImportError_) as caught:
                importer.analyse(image)
        self.assertIn("nicht Super Mario Sunshine", str(caught.exception))

    def test_missing_symbol_map_is_normal_when_revision_has_none(self):
        """GMSE01 liefert keine mario.MAP; ihr Fehlen ist kein Mangel."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root, include_map=False)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(
                register_synthetic(image, ships_symbol_map=False))
            report = importer.analyse(image)
        self.assertFalse(report.symbol_map_found)
        self.assertFalse(any("mario.MAP" in w for w in report.warnings))

    def test_warns_when_expected_symbol_map_absent(self):
        """Fehlt sie bei einer Revision, die sie mitbringt, ist das ein Hinweis."""
        with TemporaryDirectory() as tmp:
            root = Path(tmp)
            image = write_image(root, include_map=False)
            importer.SUPPORTED_REVISIONS.clear()
            importer.SUPPORTED_REVISIONS.update(
                register_synthetic(image, ships_symbol_map=True))
            report = importer.analyse(image)
        self.assertFalse(report.symbol_map_found)
        self.assertTrue(any("mario.MAP" in w for w in report.warnings))


if __name__ == "__main__":
    unittest.main()
