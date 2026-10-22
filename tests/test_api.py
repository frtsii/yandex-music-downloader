import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ymd.api import ApiTrackQuality, Container, get_download_info


class DownloadInfoTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.track = SimpleNamespace(id="153486393", client=self.client)
        self.info = {
            "codec": "mp3", "quality": "nq",
            "urls": ["https://example.test/audio"], "bitrate": 320,
        }

    def test_current_camel_case_response(self):
        self.client.request.get.return_value = {"downloadInfo": self.info}
        info = get_download_info(self.track, ApiTrackQuality.NORMAL)
        self.assertEqual(info.file_format.container, Container.MP3)
        self.assertEqual(info.urls, self.info["urls"])
        self.assertEqual(info.bitrate, 320)
        self.assertIsNone(info.decryption_key)

    def test_legacy_snake_case_response_and_encryption_key(self):
        self.client.request.get.return_value = {
            "download_info": {**self.info, "codec": "flac", "key": "0123456789abcdef"}
        }
        info = get_download_info(self.track, ApiTrackQuality.LOSSLESS)
        self.assertEqual(info.file_format.container, Container.FLAC)
        self.assertEqual(info.decryption_key, "0123456789abcdef")

    def test_missing_response_has_clear_error(self):
        for response in (None, {}, [], {"downloadInfo": None}, {"downloadInfo": []}):
            with self.subTest(response=response):
                self.client.request.get.return_value = response
                with self.assertRaisesRegex(ValueError, "не вернула сведения"):
                    get_download_info(self.track, ApiTrackQuality.NORMAL)

    def test_incomplete_info_is_rejected_before_download(self):
        for change in ({"urls": []}, {"urls": None}, {"urls": [None]},
                       {"bitrate": None}, {"quality": None}, {"codec": None}):
            with self.subTest(change=change):
                self.client.request.get.return_value = {
                    "downloadInfo": {**self.info, **change}
                }
                with self.assertRaises(ValueError):
                    get_download_info(self.track, ApiTrackQuality.NORMAL)


if __name__ == "__main__":
    unittest.main()
