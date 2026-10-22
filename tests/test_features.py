import concurrent.futures
import contextlib
import io
import json
import struct
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from mutagen.id3 import ID3
from yandex_music import Album, Artist, Client, Track

from ymd import cli, core
from ymd.api import Container
from ymd.gui import DEFAULTS, ROOT, Application, build_arguments
from ymd.lyrics import parse_lrc
from ymd.lyrics_sources import SyncedLyrics


class LyricsTests(unittest.TestCase):
    def test_formats_unicode_sorted_and_empty(self):
        self.assertEqual(parse_lrc(
            "[ar:Artist]\n[00:16.80]Вторая\n[00:12.500][01:02.003]Первая 🌟\n"
            "[01:00:00.001]\n[00:20.00]"),
            [("Первая 🌟", 12500), ("Вторая", 16800), ("", 20000),
             ("Первая 🌟", 62003), ("", 3600001)])

    def test_offset_applies_to_all_lines(self):
        self.assertEqual(parse_lrc("[00:01.00]one\n[offset:-500]"), [("one", 500)])
        self.assertEqual(parse_lrc("[offset:+1500]\n[00:00.1]a"), [("a", 1600)])

    def test_invalid_overflow_negative(self):
        self.assertEqual(parse_lrc(
            "[00:99.00]bad\n[999999999:00.0]overflow\n"
            "[00:00.0]negative\n[offset:-100]\nno timestamps\n[bad]x"), [])
        self.assertEqual(parse_lrc("[01:99:00.000]bad"), [])

    def test_nul_removed(self):
        self.assertEqual(parse_lrc("[00:01]a\x00b"), [("ab", 1000)])


class DownloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=ROOT)
        self.addCleanup(self.temp.cleanup)
        self.directory = Path(self.temp.name)
        self.track = Track(id="123", title="Песня", artists=[Artist(id=1, name="Автор")],
                           albums=[Album(id=4, title="Альбом", year=2026)])
        self.track.client = Mock()
        self.track.lyrics_info = SimpleNamespace(
            has_available_sync_lyrics=True, has_available_text_lyrics=True)
        self.track.get_lyrics = Mock(return_value=SimpleNamespace(
            fetch_lyrics=lambda: "[00:12.50]Первая\n[00:16.80]Вторая"))
        self.find_patch = patch.object(core, "find_lyrics", return_value=SyncedLyrics(
            "NetEase", "[00:12.50]Первая\n[00:16.80]Вторая", "https://example.test"))
        self.find = self.find_patch.start()
        self.addCleanup(self.find_patch.stop)
        self.info = SimpleNamespace(
            path=self.directory / "song.mp3", track=self.track,
            download_info=SimpleNamespace(file_format=SimpleNamespace(container=Container.MP3)))
        # Three valid MPEG1 Layer III frames. Audio is never transcoded.
        self.audio = (b"\xff\xfb\x90\x00" + bytes(413)) * 3

    def download(self, **kwargs):
        with patch.object(core.api, "download_track", return_value=self.audio) as fetch:
            core.download_track(self.info, **kwargs)
            fetch.assert_called_once()

    def test_sylt_round_trip_metadata_and_audio(self):
        self.download()
        tags = ID3(self.info.path)
        sylt = tags.getall("SYLT")[0]
        self.assertEqual(sylt.text, [("Первая", 12500), ("Вторая", 16800)])
        self.assertEqual((sylt.format, sylt.type, sylt.lang), (2, 1, "und"))
        self.assertEqual(str(tags["TIT2"]), "Песня")
        self.assertEqual(str(tags["TALB"]), "Альбом")
        self.assertEqual(str(tags["TPE1"]), "Автор")
        self.assertEqual(tags["WOAF"].url, "https://music.yandex.ru/album/4/track/123")
        self.assertEqual(tags.getall("USLT")[0].text, "Первая\nВторая")
        raw = self.info.path.read_bytes()
        self.assertTrue(raw.endswith(self.audio))
        self.assertFalse(list(self.directory.glob("*.lrc")))
        self.assertFalse(list(self.directory.glob("*.tmp")))
        # Independent binary decoder, not Mutagen: verify UTF-8 and timestamps.
        offset = 10
        frames = {}
        while raw[offset:offset + 4].strip(b"\0"):
            name = raw[offset:offset + 4].decode("ascii")
            size = 0
            for byte in raw[offset + 4:offset + 8]:
                size = size * 128 + byte
            frames[name] = raw[offset + 10:offset + 10 + size]
            offset += 10 + size
        data = frames["SYLT"]
        self.assertEqual(data[:6], b"\x03und\x02\x01")
        _, data = data[6:].split(b"\0", 1)
        parsed = []
        while data:
            text, data = data.split(b"\0", 1)
            parsed.append((text.decode("utf-8"), struct.unpack(">I", data[:4])[0]))
            data = data[4:]
        self.assertEqual(parsed, sylt.text)

    def test_cover_preserved(self):
        self.track.albums[0].genre = "rusrap"
        cover = core.AlbumCover(b"\xff\xd8\xfftest", core.MimeType.JPEG)
        path = self.directory / "cover.mp3"
        path.write_bytes(self.audio)
        core.set_tags(path, self.track, Container.MP3, "текст", cover, 1, [("текст", 100)])
        self.assertEqual(ID3(path).getall("APIC")[0].data, cover.data)
        self.assertEqual(str(ID3(path)["TCON"]), "Русский рэп")
        self.assertTrue(path.read_bytes().endswith(self.audio))

    def test_lyrics_failure_does_not_block_audio(self):
        self.find.side_effect = RuntimeError("unavailable")
        with self.assertLogs("ymd.core", "WARNING"):
            self.download()
        self.assertFalse(ID3(self.info.path).getall("SYLT"))

    def test_no_plain_text_fallback_without_timestamps(self):
        self.find.return_value = None
        self.download()
        self.assertFalse(ID3(self.info.path).getall("USLT"))
        self.assertFalse(ID3(self.info.path).getall("SYLT"))

    def test_disabled_makes_no_lyrics_requests(self):
        self.download(lyrics_format=core.LyricsFormat.NONE)
        self.track.get_lyrics.assert_not_called()
        self.find.assert_not_called()

    def test_no_lyrics_info(self):
        self.track.lyrics_info = None
        self.download()
        self.track.get_lyrics.assert_not_called()
        self.find.assert_called_once_with(self.track)

    def test_atomic_failure_cleans_up_and_preserves_old_file(self):
        target = self.directory / "existing.mp3"
        target.write_bytes(b"old")
        with self.assertRaises(ValueError):
            core.write_via_temporary_file(b"new", target, Mock(side_effect=ValueError("tags")))
        self.assertEqual(target.read_bytes(), b"old")
        self.assertFalse(list(self.directory.glob("*.tmp")))

    def test_atomic_replace_and_concurrent_files(self):
        target = self.directory / "shared.mp3"
        with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
            list(pool.map(lambda n: core.write_via_temporary_file(bytes([n]) * 100, target), range(4)))
        self.assertEqual(len(target.read_bytes()), 100)
        self.assertEqual(len(set(target.read_bytes())), 1)
        self.assertFalse(list(self.directory.glob("*.tmp")))

    def test_cli_lyrics_false(self):
        self.track.available = True
        client = Mock()
        client.tracks.return_value = [self.track]
        with patch.object(core, "init_client", return_value=client), \
                patch.object(core, "to_downloadable_track") as convert, \
                patch.object(core, "download_track") as download, \
                contextlib.redirect_stdout(io.StringIO()):
            convert.return_value = Mock(path=self.info.path)
            convert.return_value.download_info.bitrate = 128
            convert.return_value.download_info.file_format.codec.name = "MP3"
            cli.main(["--token", "test-only", "--track-id", "123",
                      "--lyrics=false", "--dir", str(self.directory)])
        self.assertEqual(download.call_args.kwargs["lyrics_format"], core.LyricsFormat.NONE)


class GuiSettingsTests(unittest.TestCase):
    def test_windows_names_keep_readable_punctuation(self):
        self.assertEqual(
            core.safe_path_component("Последнее лето! (Часть 1)."),
            "Последнее лето! (Часть 1)․",
        )
        self.assertEqual(
            core.safe_path_component("Shh__... wow, pt.1 [demo]"),
            "Shh__... wow, pt.1 [demo]",
        )
        self.assertEqual(core.safe_path_component("Shh..."), "Shh…")
        self.assertEqual(core.safe_path_component('A:B?C*D"E'), "A_B_C_D_E")
        self.assertEqual(core.safe_path_component("CON"), "_CON")

    def test_automatic_library_layout(self):
        self.assertEqual(
            cli.automatic_path_pattern("playlist", "Мой плейлист"),
            Path("Мой плейлист/#track-artist - #title"),
        )
        self.assertEqual(
            cli.automatic_path_pattern("album", "MILITANTUM", "тёмный принц"),
            Path("тёмный принц - MILITANTUM/#number-padded - #title"),
        )
        self.assertEqual(
            cli.automatic_path_pattern("artist", artist="тёмный принц"),
            Path("тёмный принц - дискография/#album/#number-padded - #title"),
        )

    def test_supported_urls(self):
        for url, expected in (
            ("https://music.yandex.ru/album/1/track/2?x=y", ("track", "2")),
            ("https://music.yandex.ru/album/1/", ("album", "1")),
            ("https://music.yandex.kz/artist/3", ("artist", "3")),
            ("https://music.yandex.ru/users/user.name/playlists/4", ("playlist", "user.name/4")),
            ("https://music.yandex.ru/playlists/lk.1d1908e3-5734-4dd7-9f95-b0b0ebd006ae?utm_source=desktop",
             ("playlist", "uuid:lk.1d1908e3-5734-4dd7-9f95-b0b0ebd006ae")),
        ):
            self.assertEqual(cli.parse_url(url), expected)

    def test_bad_urls(self):
        for url in ("https://evil.test/track/1", "file:///track/1", "hello"):
            with self.assertRaises(ValueError):
                cli.parse_url(url)

    def test_default_arguments(self):
        args = build_arguments(DEFAULTS)
        self.assertIn("--embed-cover", args)
        self.assertIn("embed", args)
        self.assertNotIn("--token", args)

    def test_cannot_leave_project(self):
        for values in ({"directory": ".."}, {"pattern": "../#title"},
                       {"pattern": str(ROOT / "#title")}, {"pattern": "#oops"},
                       {"timeout": "0"}, {"tries": "-1"}, {"cover": "20"}):
            with self.subTest(values=values), self.assertRaises(ValueError):
                build_arguments({**DEFAULTS, **values})

    def test_settings_ignore_token_and_invalid_choices(self):
        self.assertEqual(Application.valid_settings(
            {"token": "secret", "quality": "invalid", "skip_existing": "not boolean",
             "directory": "Music"}), {"directory": "Music"})


if __name__ == "__main__":
    unittest.main()
