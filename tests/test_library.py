import hashlib
from pathlib import Path
import struct
import tempfile
import unittest

from mutagen.flac import FLAC
from mutagen.id3 import ID3, TIT2, TPE1
from mutagen.mp4 import MP4

from ymd.gui import ROOT
from ymd.library import embed_existing
from ymd.lyrics import parse_lrc


def mdat_hash(path):
    raw = path.read_bytes()
    pos = 0
    digest = hashlib.sha256()
    found = False
    while pos + 8 <= len(raw):
        size, kind = struct.unpack(">I4s", raw[pos:pos + 8])
        header = 8
        if size == 1:
            size = struct.unpack(">Q", raw[pos + 8:pos + 16])[0]
            header = 16
        elif size == 0:
            size = len(raw) - pos
        if size < header or pos + size > len(raw):
            raise ValueError("Invalid MP4")
        if kind == b"mdat":
            digest.update(raw[pos + header:pos + size])
            found = True
        pos += size
    if not found:
        raise ValueError("Missing mdat")
    return digest.hexdigest()


class LocalLyricsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()

    def test_mp3_adds_sylt_and_backup_without_changing_audio(self):
        path = self.root / "sample.mp3"
        audio = (b"\xff\xfb\x90\x00" + bytes(413)) * 100
        path.write_bytes(audio)
        tags = ID3()
        tags.add(TIT2(encoding=3, text="Test"))
        tags.add(TPE1(encoding=3, text="Artist"))
        tags.save(path)
        original = path.read_bytes()
        embed_existing(path, "[00:00.100]first\n[00:01.000]second", self.root)
        self.assertEqual(ID3(path).getall("SYLT")[0].text, [("first", 100), ("second", 1000)])
        self.assertEqual(str(ID3(path)["TIT2"]), "Test")
        self.assertTrue(path.read_bytes().endswith(audio))
        self.assertEqual((self.root / "lyrics-backups/sample.mp3").read_bytes(), original)

    def test_flac_retains_lrc_timestamps(self):
        path = self.root / "sample.flac"
        info = bytes(10) + ((44100 << 44) | (1 << 41) | (15 << 36) | 6_000_000).to_bytes(8, "big") + bytes(16)
        payload = b"test-audio-payload"
        path.write_bytes(b"fLaC\x80\x00\x00\x22" + info + payload)
        tags = FLAC(path)
        tags["title"] = "Test"
        tags["artist"] = "Artist"
        tags.save()
        embed_existing(path, "[00:01]first\n[00:02]second", self.root)
        self.assertEqual(parse_lrc(FLAC(path)["lyrics"][0]), [("first", 1000), ("second", 2000)])
        self.assertTrue(path.read_bytes().endswith(payload))

    def test_real_m4a_copy_preserves_audio_cover_and_other_tags(self):
        candidates = list((ROOT / "Music").rglob("11 - kiss me.m4a"))
        if not candidates:
            self.skipTest("Local M4A sample not present")
        source = candidates[0]
        path = self.root / "sample.m4a"
        original = source.read_bytes()
        path.write_bytes(original)
        before = dict(MP4(path).tags)
        audio_hash = mdat_hash(path)
        lrc = "[00:01.123]Test line\n[00:04.500]Second line"
        embed_existing(path, lrc, self.root)
        after = dict(MP4(path).tags)
        self.assertEqual(parse_lrc(after.pop("\xa9lyr")[0]), parse_lrc(lrc))
        before.pop("\xa9lyr", None)
        self.assertEqual(before, after)
        self.assertEqual(mdat_hash(path), audio_hash)
        self.assertEqual(source.read_bytes(), original)
        self.assertEqual((self.root / "lyrics-backups/sample.m4a").read_bytes(), original)
