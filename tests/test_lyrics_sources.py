import base64
import json
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest.mock import Mock

from ymd.lyrics_sources import (
    Http, LyricsResolver, Song, SyncedLyrics, kugou, lrclib, matches, netease, qqmusic, valid_lrc,
)

SONG = Song("kiss me", ("тёмный принц",), "MILITANTUM", 134.4)
LRC = "[00:01.000]Тестовая строка\n[00:04.500]Вторая строка"


class ProviderTests(unittest.TestCase):
    def test_netease_search_and_lyrics(self):
        http = Mock()
        http.request.side_effect = [
            {"result": {"songs": [
                {"id": 1, "name": "kiss me", "artists": [{"name": "Другой"}], "duration": 134400},
                {"id": 2, "name": "kiss me", "artists": [{"name": "тёмный принц"}], "duration": 134400},
            ]}},
            {"lrc": {"lyric": LRC}},
        ]
        result = netease(SONG, http)
        self.assertEqual(result.lrc, LRC)
        self.assertEqual(http.request.call_args.kwargs["params"]["id"], 2)

    def test_lrclib_rejects_unsynced_and_wrong_version(self):
        http = Mock()
        http.request.return_value = [
            dict(trackName="kiss me", artistName="тёмный принц", duration=180, syncedLyrics=LRC),
            dict(trackName="kiss me", artistName="тёмный принц", duration=134, syncedLyrics=None),
            dict(id=3, trackName="kiss me", artistName="тёмный принц", duration=134, syncedLyrics=LRC),
        ]
        self.assertIn("/3", lrclib(SONG, http).url)

    def test_qq_success_and_service_error(self):
        http = Mock()
        search = {"code": 0, "data": {"song": {"list": [
            {"songname": "kiss me (Explicit)", "singer": [{"name": "тёмный принц"}],
             "interval": 134, "songmid": "abc"},
        ]}}}
        http.request.side_effect = [search, {"code": 0, "lyric": LRC}]
        self.assertEqual(qqmusic(SONG, http).source, "QQ Music")
        http.request.side_effect = [search, {"code": -1901}]
        with self.assertRaises(ValueError):
            qqmusic(SONG, http)

    def test_kugou_decode_lrc(self):
        http = Mock()
        http.request.side_effect = [
            {"candidates": [{"song": "kiss me", "singer": "тёмный принц",
                             "duration": 134400, "id": "1", "accesskey": "test"}]},
            {"content": base64.b64encode(LRC.encode()).decode()},
        ]
        self.assertEqual(kugou(SONG, http).lrc, LRC)

    def test_match_and_fake_timestamps(self):
        self.assertTrue(matches(SONG, "Kiss Me (Explicit)", ["темный принц"], 135))
        self.assertFalse(matches(SONG, "kiss me (remix)", ["тёмный принц"], 134))
        self.assertFalse(valid_lrc("Текст без меток"))
        self.assertFalse(valid_lrc("[00:00]one\n[00:00]two"))
        self.assertFalse(valid_lrc("[00:01]one\n[05:00]two", 134))
        self.assertTrue(valid_lrc(LRC, 134))

    def test_order_errors_and_cache(self):
        providers = [
            ("NetEase", Mock(side_effect=ValueError())),
            ("LRCLIB", Mock(return_value=None)),
            ("QQ Music", Mock(return_value=SyncedLyrics("QQ Music", LRC, ""))),
            ("KuGou", Mock()),
        ]
        resolver = LyricsResolver(providers=providers)
        self.assertEqual(resolver.find(SONG).source, "QQ Music")
        resolver.find(SONG)
        for _, provider in providers[:3]:
            provider.assert_called_once()
        providers[3][1].assert_not_called()
        self.assertIn("NetEase", resolver.cooldowns)

    def test_hung_source_does_not_block_or_accumulate(self):
        release = threading.Event()
        def slow(song, http):
            release.wait(2)
        resolver = LyricsResolver(source_timeout=.1, total_timeout=.4,
                                   providers=[("slow", slow), ("good", lambda s, h: SyncedLyrics("good", LRC, ""))])
        start = time.monotonic()
        try:
            self.assertEqual(resolver.find(SONG).source, "good")
            self.assertLess(time.monotonic() - start, .6)
            thread = resolver.active["slow"]
            resolver.find(Song("other", SONG.artists))
            self.assertIs(resolver.active["slow"], thread)
        finally:
            release.set()

    def test_total_deadline(self):
        release = threading.Event()
        def slow(song, http):
            release.wait(2)
        resolver = LyricsResolver(source_timeout=.04, total_timeout=.06,
                                   providers=[("a", slow), ("b", slow), ("c", slow)])
        start = time.monotonic()
        try:
            with self.assertLogs("ymd.lyrics_sources", "WARNING"):
                self.assertIsNone(resolver.find(SONG))
            self.assertLess(time.monotonic() - start, .3)
            self.assertNotIn("c", resolver.active)
        finally:
            release.set()

    def test_http_uses_no_yandex_authorization(self):
        observed = []
        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                observed.append(self.headers.get("Authorization"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(json.dumps({"syncedLyrics": LRC}).encode())
            def log_message(self, *args):
                pass
        server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        http = Http(time.monotonic() + 3)
        try:
            result = http.request("GET", f"http://127.0.0.1:{server.server_port}/lyrics")
            self.assertEqual(result["syncedLyrics"], LRC)
            self.assertEqual(observed, [None])
        finally:
            http.close()
            server.shutdown()
            server.server_close()
            worker.join()


if __name__ == "__main__":
    unittest.main()
