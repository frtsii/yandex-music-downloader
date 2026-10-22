"""Local desktop interface. Settings and downloads stay in the project directory."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox
from ymd.desktop import DesktopUI

from ymd.cli import contained_path, parse_url

ROOT = Path(__file__).resolve().parent.parent
SETTINGS = ROOT / "gui-settings.json"
QUALITIES = {"Низкое · AAC 64": "0", "Оптимальное · AAC 192": "1", "Лучшее · FLAC": "2"}
LYRICS = {
    "Встроить таймкоды (SYLT / LRC)": "embed",
    "Обычный текст из найденного LRC": "text",
    "Встроить + отдельный файл LRC": "lrc",
    "Не загружать текст": "none",
}
PATTERNS = (
    "#album-artist/#album/#number-padded - #title",
    "#track-artist/#title",
    "#track-artist/#year - #album/#number-padded - #title",
    "#title - #track-artist",
)
DEFAULTS = {
    "quality": list(QUALITIES)[1], "lyrics": next(iter(LYRICS)),
    "directory": "Music", "pattern": PATTERNS[0], "cover": "400",
    "skip_existing": True, "embed_cover": True, "only_music": False,
    "stick_to_artist": False, "unsafe_path": False,
    "delay": "0", "timeout": "20", "tries": "20", "retry_delay": "5",
    "compatibility": "1",
}


def build_arguments(values: dict) -> list[str]:
    """Validate form values before starting any network activity."""
    directory = contained_path(ROOT, Path(values["directory"].strip() or "Music"))
    pattern = values["pattern"].strip()
    if not pattern or Path(pattern).is_absolute() or Path(pattern).drive:
        raise ValueError("Правило имени должно быть непустым относительным путём")
    if any(part in (".", "..") for part in pattern.replace("\\", "/").split("/")):
        raise ValueError("В правиле имени нельзя использовать . или ..")
    if any(char in pattern for char in '<>:"|?*\x00'):
        raise ValueError('В правиле имени недопустимы символы <>:"|?*')
    allowed = {"#number", "#number-padded", "#track-artist", "#album-artist",
               "#title", "#album", "#year", "#artist-id", "#album-id", "#track-id"}
    import re
    if set(re.findall(r"#[\w-]+", pattern)) - allowed:
        raise ValueError("Неизвестный заполнитель в правиле имени")
    args = ["--workspace-root", str(ROOT), "--dir", str(directory),
            "--path-pattern", pattern, "--quality", QUALITIES[values["quality"]],
            "--lyrics-format", LYRICS[values["lyrics"]]]
    for key, minimum in (("delay", 0), ("timeout", 1), ("tries", 0), ("retry_delay", 0)):
        try:
            number = int(values[key])
        except ValueError:
            raise ValueError(f"{key}: нужно целое число")
        if number < minimum:
            raise ValueError(f"{key}: минимальное значение — {minimum}")
        args.extend(["--" + key.replace("_", "-"), str(number)])
    cover = values["cover"].strip()
    if cover != "original" and (not cover.isdigit() or int(cover) < 100):
        raise ValueError("Размер обложки: число от 100 или original")
    if values["compatibility"] not in ("0", "1"):
        raise ValueError("Уровень совместимости: 0 или 1")
    args.extend(["--cover-resolution", cover, "--compatibility-level", values["compatibility"]])
    for key in ("skip_existing", "embed_cover", "only_music", "stick_to_artist", "unsafe_path"):
        if values[key]:
            args.append("--" + key.replace("_", "-"))
    return args


class Application(DesktopUI):
    def __init__(self, window: tk.Tk):
        self.window = window
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.process = None
        self.process_lock = threading.Lock()
        self.running = False
        self.closing = False
        self.profiles = {}
        values = DEFAULTS.copy()
        self.animate_background = True
        settings_error = None
        try:
            if SETTINGS.exists():
                data = json.loads(SETTINGS.read_text(encoding="utf-8"))
                self.animate_background = data.get("animation", True) is not False
                values.update(self.valid_settings(data.get("last", {})))
                self.profiles = {
                    name: self.valid_settings(profile)
                    for name, profile in data.get("profiles", {}).items()
                    if isinstance(name, str) and isinstance(profile, dict)
                }
        except (OSError, ValueError, TypeError, AttributeError):
            settings_error = "Не удалось прочитать настройки. Использованы стандартные."
        self.variables = {
            key: (tk.BooleanVar(value=value) if isinstance(value, bool) else tk.StringVar(value=value))
            for key, value in values.items()
        }
        self.token = tk.StringVar()
        self.profile = tk.StringVar(value="Мои настройки")
        self.status = tk.StringVar(value="Ожидание ссылки")
        self.build_ui()
        if settings_error:
            self.append_log(settings_error + "\n")
        window.protocol("WM_DELETE_WINDOW", self.close)
        self.poll_job = window.after(100, self.poll)

    @staticmethod
    def valid_settings(data):
        data = dict(data)
        old_lyrics = {
            "Встроенный текст · SYLT в MP3": next(iter(LYRICS)),
            "Только обычный встроенный текст": list(LYRICS)[1],
            "Отдельный файл LRC": list(LYRICS)[2],
        }
        if data.get("lyrics") in old_lyrics:
            data["lyrics"] = old_lyrics[data["lyrics"]]
        return {key: value for key, value in data.items()
                if key in DEFAULTS and type(value) is type(DEFAULTS[key])
                and (key != "quality" or value in QUALITIES)
                and (key != "lyrics" or value in LYRICS)}

    def toggle_token(self):
        self.token_entry.configure(show="" if self.token_entry.cget("show") else "•")

    def values(self):
        return {key: variable.get() for key, variable in self.variables.items()}

    def save_settings(self):
        # Never serialize the token or the pasted links.
        contained_path(ROOT, SETTINGS)
        temp = contained_path(ROOT, SETTINGS.with_suffix(".tmp"))
        temp.write_text(json.dumps({"last": self.values(), "profiles": self.profiles,
                                   "animation": self.animations.get()},
                                   ensure_ascii=False, indent=2), encoding="utf-8")
        temp.replace(SETTINGS)

    def save_profile(self):
        name = self.profile.get().strip()
        if not name:
            messagebox.showerror("Набор правил", "Введите название набора", parent=self.window)
            return
        try:
            build_arguments(self.values())
            self.profiles[name] = self.values()
            self.save_settings()
            self.profile_combo.configure(values=list(self.profiles))
            self.status.set("Набор правил сохранён")
        except (ValueError, OSError) as error:
            messagebox.showerror("Настройки", str(error), parent=self.window)

    def apply_profile(self):
        if self.running or getattr(self, "updating_lyrics", False):
            return
        profile = self.profiles.get(self.profile.get())
        if profile is None:
            messagebox.showinfo("Набор правил", "Выберите ранее сохранённый набор", parent=self.window)
            return
        for key, value in {**DEFAULTS, **profile}.items():
            self.variables[key].set(value)
        self.status.set("Набор правил применён")

    def choose_directory(self):
        path = filedialog.askdirectory(parent=self.window, initialdir=ROOT, title="Папка внутри проекта")
        if path:
            try:
                target = contained_path(ROOT, Path(path))
                self.variables["directory"].set(str(target.relative_to(ROOT)))
            except ValueError as error:
                messagebox.showerror("Папка", str(error), parent=self.window)

    def open_directory(self):
        try:
            path = contained_path(ROOT, Path(self.variables["directory"].get()))
            path.mkdir(parents=True, exist_ok=True)
            os.startfile(path)
        except (ValueError, OSError) as error:
            messagebox.showerror("Папка", str(error), parent=self.window)

    def start(self):
        if self.running or getattr(self, "updating_lyrics", False):
            return
        try:
            token = self.token.get().strip()
            if not token:
                self.open_settings()
                self.token_entry.focus_set()
                raise ValueError("Введите OAuth-токен")
            links = list(dict.fromkeys(line.strip() for line in self.links.get("1.0", "end").splitlines() if line.strip()))
            if not links:
                raise ValueError("Вставьте хотя бы одну ссылку")
            for link in links:
                parse_url(link)
            arguments = build_arguments(self.values())
            self.save_settings()
        except (ValueError, OSError) as error:
            messagebox.showerror("Проверьте настройки", str(error), parent=self.window)
            return
        self.running = True
        self.cancel.clear()
        self.start_button.configure(state="disabled")
        self.stop_button.configure(state="normal")
        self.status.set("Загрузка…")
        self.percent.configure(text="…")
        self.detail.configure(text="Подключение к Яндекс Музыке")
        self.close_settings()
        self.update_placeholder()
        self.progress.configure(mode="indeterminate")
        self.progress.start()
        self.append_log("\nНачата загрузка. Изменения правил применятся при следующем запуске.\n")
        threading.Thread(target=self.download, args=(links, arguments, token), daemon=True).start()

    def download(self, links, arguments, token):
        failed = 0
        try:
            env = os.environ.copy()
            env.update(YMD_GUI_EVENTS="1", YMD_TOKEN=token, PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1")
            for index, link in enumerate(links, 1):
                if self.cancel.is_set():
                    break
                self.events.put(("log", f"\nСсылка {index}/{len(links)}: {link}\n"))
                with self.process_lock:
                    if self.cancel.is_set():
                        break
                    process = subprocess.Popen(
                        [sys.executable, "-u", "-m", "ymd", *arguments, "--url", link],
                        cwd=ROOT, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        stdin=subprocess.DEVNULL, text=True, encoding="utf-8", errors="replace",
                        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                    )
                    self.process = process
                try:
                    for line in process.stdout:
                        line = line.replace(token, "[токен скрыт]")
                        if line.startswith("@YMD "):
                            try:
                                item = json.loads(line[5:])
                                item["kind"] = parse_url(link)[0]
                                self.events.put(("downloaded", item))
                            except (ValueError, TypeError):
                                self.events.put(("log", "Некорректное событие загрузчика.\n"))
                        else:
                            self.events.put(("log", line))
                    code = process.wait()
                    if code and not self.cancel.is_set():
                        failed += 1
                        self.events.put(("log", f"Ошибка загрузки ссылки (код {code}).\n"))
                finally:
                    process.stdout.close()
                    if process.poll() is None:
                        process.terminate()
                    process.wait()
                    with self.process_lock:
                        self.process = None
                    # Only this completed child's temporary files, inside our root.
                    for path in ROOT.rglob(f".yandex-music-downloader.{process.pid}.*.tmp"):
                        try:
                            contained_path(ROOT, path).unlink(missing_ok=True)
                        except (OSError, ValueError):
                            self.events.put(("log", "Не удалось удалить временный файл загрузки.\n"))
            result = "Остановлено" if self.cancel.is_set() else (
                f"Готово. Ошибок ссылок: {failed}" if failed else "Загрузка завершена")
        except Exception as error:
            result = "Ошибка запуска"
            self.events.put(("log", str(error).replace(token, "[токен скрыт]") + "\n"))
        self.events.put(("done", result))

    def stop(self):
        self.cancel.set()
        self.status.set("Остановка…")
        self.stop_button.configure(state="disabled")
        with self.process_lock:
            if self.process is not None and self.process.poll() is None:
                self.process.terminate()

    def append_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text)
        if int(self.log._textbox.index("end-1c").split(".")[0]) > 3000:
            self.log.delete("1.0", "1000.0")
        self.log.see("end")
        self.log.configure(state="disabled")

    def poll(self):
        for _ in range(200):
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self.append_log(text)
                if "Загружается " in text:
                    self.detail.configure(text=Path(text.split("Загружается ", 1)[1].strip()).name[:55])
                elif "Текст с таймкодами:" in text:
                    self.detail.configure(text=text.split("Текст с таймкодами:", 1)[1].strip() + " · LRC найден")
            elif kind in ("downloaded", "history"):
                self.add_history(text)
                if kind == "downloaded":
                    self.detail.configure(text=f"Сохранён: {text.get('title', '')}"[:60])
                    total = text.get("total")
                    if isinstance(total, (int, float)) and total > 0:
                        self.percent.configure(text=f"{min(100, round(text.get('index', 0) / total * 100))}%")
            elif kind == "scan_done":
                self.scanning = False
            elif kind == "lyrics_done":
                self.updating_lyrics = False
                self.status.set("Проверка LRC завершена")
                self.start_button.configure(state="normal")
                if self.closing:
                    self.destroy()
                    return
            elif kind == "done":
                self.running = False
                self.status.set(text)
                self.append_log(text + "\n")
                self.progress.stop()
                self.progress.configure(mode="determinate")
                self.progress.set(1 if text == "Загрузка завершена" else 0)
                self.percent.configure(text="100%" if text == "Загрузка завершена" else "—")
                self.detail.configure(text=text)
                self.start_button.configure(state="normal")
                self.stop_button.configure(state="disabled")
                if self.closing:
                    self.destroy()
                    return
        self.poll_job = self.window.after(100, self.poll)

    def close(self):
        if getattr(self, "updating_lyrics", False):
            self.closing = True
            self.status.set("Завершаем запись тегов…")
        elif self.running:
            self.closing = True
            self.stop()
        else:
            self.destroy()

    def destroy(self):
        if self.animation_job:
            self.window.after_cancel(self.animation_job)
        if getattr(self, "poll_job", None):
            self.window.after_cancel(self.poll_job)
        self.window.destroy()


def main():
    from customtkinter import CTk
    window = CTk()
    Application(window)
    window.mainloop()


if __name__ == "__main__":
    main()
