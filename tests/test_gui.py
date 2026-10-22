"""Exercise the real Tk window with a fake downloader, without network access."""
import io
import json
import tempfile
import time
import tkinter as tk
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ymd import gui


class WindowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(dir=gui.ROOT)
        self.addCleanup(self.temp.cleanup)
        self.settings = Path(self.temp.name) / "settings.json"
        self.root_patch = patch.object(gui, "ROOT", Path(self.temp.name))
        self.root_patch.start()
        self.addCleanup(self.root_patch.stop)
        self.patch_settings = patch.object(gui, "SETTINGS", self.settings)
        self.patch_settings.start()
        self.addCleanup(self.patch_settings.stop)
        self.window = tk.Tk()
        self.window.withdraw()
        self.app = gui.Application(self.window)
        self.addCleanup(self.cleanup_window)

    def cleanup_window(self):
        # Cancel Tcl timers without deleting callbacks owned by child widgets.
        for job in self.window.tk.call("after", "info"):
            self.window.tk.call("after", "cancel", job)
        self.app.destroy()

    def test_profiles_roundtrip_excludes_token_and_urls(self):
        self.app.token.set("test-secret")
        self.app.links.insert("1.0", "https://music.yandex.ru/track/1")
        self.app.profile.set("Мой набор")
        self.app.variables["pattern"].set("#title")
        self.app.save_profile()
        data = json.loads(self.settings.read_text(encoding="utf-8"))
        self.assertEqual(data["profiles"]["Мой набор"]["pattern"], "#title")
        self.assertNotIn("test-secret", self.settings.read_text(encoding="utf-8"))
        self.assertNotIn("https://", self.settings.read_text(encoding="utf-8"))
        self.app.variables["pattern"].set("#album")
        self.app.apply_profile()
        self.assertEqual(self.app.variables["pattern"].get(), "#title")

    def test_queue_and_completion_redacts_token(self):
        self.app.token.set("test-secret")
        self.app.links.insert("1.0", "https://music.yandex.ru/track/1\n"
                              "https://music.yandex.ru/album/2\nhttps://music.yandex.ru/track/1")

        def process(*args, **kwargs):
            obj = Mock(pid=999999999)
            obj.stdout = io.StringIO("test-secret progress\n")
            obj.wait.return_value = 0
            obj.poll.return_value = 0
            return obj

        with patch.object(gui.subprocess, "Popen", side_effect=process) as popen:
            self.app.start()
            deadline = time.monotonic() + 5
            while self.app.running and time.monotonic() < deadline:
                self.window.update()
                time.sleep(0.02)
            self.assertFalse(self.app.running)
            self.assertEqual(popen.call_count, 2)
            self.assertEqual(self.app.status.get(), "Загрузка завершена")
            output = self.app.log.get("1.0", "end")
            self.assertNotIn("test-secret", output)
            self.assertIn("[токен скрыт]", output)
            self.assertEqual(popen.call_args.kwargs["env"]["YMD_TOKEN"], "test-secret")
            self.assertNotIn("test-secret", popen.call_args.args[0])

    def test_stop_terminates_active_child(self):
        self.app.process = Mock()
        self.app.process.poll.return_value = None
        self.app.stop()
        self.assertTrue(self.app.cancel.is_set())
        self.app.process.terminate.assert_called_once()

    def test_default_filters_and_settings_panel(self):
        self.assertEqual(self.app.type_filter.get(), "Все форматы")
        self.assertEqual(self.app.lyrics_filter.get(), "Любой текст")
        self.app.open_settings()
        self.assertEqual(self.app.settings_panel.winfo_manager(), "place")
        self.app.close_settings()
        self.assertEqual(self.app.settings_panel.winfo_manager(), "")

    def test_history_and_download_event(self):
        record = {"path": str(Path(self.temp.name) / "test.m4a"),
                  "title": "Test", "artist": "Artist", "album": "Album",
                  "source": "NetEase", "index": 1, "total": 2}
        self.app.events.put(("downloaded", record))
        self.app.poll()
        self.assertEqual(self.app.percent.cget("text"), "50%")
        self.assertEqual(self.app.history[0]["source"], "NetEase")
        self.assertTrue((Path(self.temp.name) / "gui-history.json").exists())


if __name__ == "__main__":
    unittest.main()
