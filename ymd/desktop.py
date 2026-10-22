"""Two-column desktop layout with animated spectrum and a settings drawer."""
import json
import math
import os
from pathlib import Path
import random
import threading
import tkinter as tk
from tkinter import messagebox

import customtkinter as ctk
ctk.set_appearance_mode("dark")

BG = "#0b101b"
PANEL = "#171f30"
FIELD = "#202a3d"
BORDER = "#344055"
TEXT = "#e9edf7"
MUTED = "#94a3bd"
ACCENT = "#54dec6"
PURPLE = "#aa8bfa"


class DesktopUI:
    def build_ui(self):
        from ymd.gui import ROOT
        self.window.title("Yandex Music Downloader")
        self.window.geometry("1080x740")
        self.window.minsize(960, 640)
        self.window.configure(bg=BG)
        self.window.after(200, self.style_titlebar)
        self.window.option_add("*Font", ("Segoe UI", 10))
        self.canvas = tk.Canvas(self.window, bg=BG, highlightthickness=0)
        self.canvas.place(relwidth=1, relheight=1)
        self.animations = tk.BooleanVar(value=self.animate_background)
        self.frame = 0
        self.animation_job = None
        rng = random.Random(42)
        self.particles = [(rng.random(), rng.random(), rng.uniform(.5, 1.5)) for _ in range(35)]
        self.draw_background()

        self.header = ctk.CTkFrame(self.window, fg_color=BG, corner_radius=0)
        tk.Place.place_configure(self.header, relx=.025, y=20, relwidth=.95, height=65)
        self.button(self.header, "☰", self.toggle_menu, width=42, height=42).pack(side="left", padx=(0, 12))
        ctk.CTkLabel(self.header, text="↓", width=46, height=46, corner_radius=10,
                     fg_color=ACCENT, text_color=BG, font=("Segoe UI", 32, "bold")).pack(side="left", padx=(0, 14))
        heading = ctk.CTkFrame(self.header, fg_color="transparent")
        heading.pack(side="left", fill="x")
        ctk.CTkLabel(heading, text="Yandex Music Downloader", anchor="w",
                     text_color=TEXT, font=("Segoe UI", 26, "bold")).pack(anchor="w")
        ctk.CTkLabel(heading, text="Музыка, обложки и синхронизированные тексты",
                     text_color=MUTED, font=("Segoe UI", 12)).pack(anchor="w")

        left = self.card(self.window)
        tk.Place.place_configure(left, relx=.025, y=100, relwidth=.465, height=235)
        links_row = ctk.CTkFrame(left, fg_color=FIELD, corner_radius=9)
        links_row.pack(fill="x", padx=20, pady=(20, 12))
        ctk.CTkLabel(links_row, text="↗", width=34, text_color=ACCENT, font=("Segoe UI", 22)).pack(side="left", padx=(8, 0))
        self.links = ctk.CTkTextbox(links_row, height=55, fg_color=FIELD,
                                  text_color=TEXT, font=("Segoe UI", 13), wrap="word")
        self.links.pack(side="left", fill="x", expand=True, padx=(0, 6), pady=3)
        self.placeholder = ctk.CTkLabel(self.links, text="Вставьте ссылки Яндекс Музыки",
                                       text_color=MUTED, font=("Segoe UI", 13))
        self.placeholder.place(x=8, y=10)
        self.placeholder.bind("<Button-1>", lambda e: self.links.focus_set())
        self.links.bind("<FocusIn>", self.update_placeholder)
        self.links.bind("<FocusOut>", self.update_placeholder)
        self.links.bind("<KeyRelease>", self.update_placeholder)
        folder = ctk.CTkFrame(left, fg_color=FIELD, corner_radius=9, height=46)
        folder.pack(fill="x", padx=20)
        folder.pack_propagate(False)
        ctk.CTkLabel(folder, text="▱", text_color=ACCENT, width=38, font=("Segoe UI", 22)).pack(side="left", padx=4)
        self.directory_entry = ctk.CTkEntry(folder, textvariable=self.variables["directory"],
                                            border_width=0, fg_color=FIELD)
        self.directory_entry.pack(side="left", fill="x", expand=True)
        self.button(folder, "✎", self.choose_directory, width=36, height=30).pack(side="right", padx=5)
        actions = ctk.CTkFrame(left, fg_color="transparent")
        actions.pack(fill="x", padx=20, pady=(17, 12))
        self.button(actions, "⚙  Настройки", self.open_settings, width=120).pack(side="left")
        self.stop_button = self.button(actions, "Стоп", self.stop, width=60, state="disabled")
        self.stop_button.pack(side="left", padx=7)
        self.start_button = self.button(actions, "↓  Скачать", self.start, width=133, height=46, primary=True)
        self.start_button.pack(side="right")

        state = self.card(self.window)
        tk.Place.place_configure(state, relx=.025, y=350, relwidth=.465, height=143)
        line = ctk.CTkFrame(state, fg_color="transparent")
        line.pack(fill="x", padx=20, pady=(18, 8))
        self.status_label = ctk.CTkLabel(line, textvariable=self.status, text_color=TEXT,
                                        font=("Segoe UI", 17, "bold"), anchor="w")
        self.status_label.pack(side="left", fill="x", expand=True)
        self.percent = ctk.CTkLabel(line, text="0%", font=("Segoe UI", 22, "bold"), text_color=ACCENT)
        self.percent.pack(side="right")
        self.detail = ctk.CTkLabel(state, text="Готово к загрузке", text_color=MUTED, anchor="w")
        self.detail.pack(fill="x", padx=20)
        self.progress = ctk.CTkProgressBar(state, height=7, fg_color=FIELD, progress_color=ACCENT,
                                         mode="determinate")
        self.progress.set(0)
        self.progress.pack(fill="x", padx=20, pady=(12, 18))
        self.sources_label = ctk.CTkLabel(
            self.window, text="LRC  ·  NetEase → LRCLIB → QQ Music → KuGou",
            text_color=MUTED, font=("Segoe UI", 11), fg_color=BG,
        )
        self.sources_label.place(relx=.035, y=505)

        right = self.card(self.window)
        tk.Place.place_configure(right, relx=.505, y=100, relwidth=.47, relheight=1, height=-125)
        tabbar = ctk.CTkFrame(right, fg_color="transparent")
        tabbar.pack(fill="x", padx=18, pady=(18, 10))
        self.history_button = self.button(tabbar, "▣  История", lambda: self.show_tab("history"), primary=True, width=110)
        self.history_button.pack(side="left", padx=(0, 8))
        self.log_button = self.button(tabbar, "▤  Журнал", lambda: self.show_tab("log"), width=105)
        self.log_button.pack(side="left")
        self.button(tabbar, "↻", self.scan_library, width=34).pack(side="right")
        self.history_page = ctk.CTkFrame(right, fg_color="transparent")
        self.log_page = ctk.CTkFrame(right, fg_color="transparent")
        self.history_page.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        filters = ctk.CTkFrame(self.history_page, fg_color="transparent")
        filters.pack(fill="x", pady=(0, 8))
        self.type_filter = self.combo(filters, ["Все форматы", "MP3", "M4A", "FLAC"], width=115,
                                      command=lambda _: self.render_history())
        self.type_filter.pack(side="left", padx=(0, 6))
        self.lyrics_filter = self.combo(filters, ["Любой текст", "Есть LRC", "Без LRC"], width=120,
                                        command=lambda _: self.render_history())
        self.lyrics_filter.pack(side="left", padx=(0, 6))
        self.search = ctk.CTkEntry(filters, placeholder_text="Исполнитель / трек", fg_color=FIELD, border_color=BORDER)
        self.search.pack(side="left", fill="x", expand=True)
        self.search.bind("<KeyRelease>", lambda e: self.render_history())
        self.history_list = ctk.CTkScrollableFrame(self.history_page, fg_color="transparent")
        self.history_list.pack(fill="both", expand=True)
        self.log = ctk.CTkTextbox(self.log_page, fg_color=BG, text_color=MUTED,
                                 font=("Consolas", 11), state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)
        self.history = []
        self.history_path = ROOT / "gui-history.json"
        try:
            from ymd.cli import contained_path
            contained_path(ROOT, self.history_path)
            records = json.loads(self.history_path.read_text(encoding="utf-8"))
            for item in records:
                if not isinstance(item, dict) or not isinstance(item.get("path"), str):
                    continue
                try:
                    contained_path(ROOT, Path(item["path"]))
                    self.history.append(item)
                except ValueError:
                    continue
        except (OSError, ValueError, TypeError):
            pass
        self.render_history()
        self.menu = ctk.CTkFrame(self.window, fg_color=PANEL, border_color=BORDER, border_width=1,
                                 width=76, corner_radius=12)
        for label, action in (("↓", self.hide_menu), ("⚙", self.open_settings),
                              ("◈", self.toggle_animation), ("▱", self.open_directory)):
            self.button(self.menu, label, action, width=48, height=48).pack(padx=14, pady=8)
        self.button(self.menu, "×", self.hide_menu, width=48, height=42).pack(side="bottom", padx=14, pady=14)
        self.menu_visible = False
        self.settings_panel = None
        self.build_settings()
        self.window.bind("<Escape>", lambda e: self.close_settings())
        if not self.history:
            self.scan_library()

    def card(self, parent):
        return ctk.CTkFrame(parent, fg_color=PANEL, bg_color=BG, corner_radius=10,
                            border_width=1, border_color=BORDER)

    def button(self, parent, text, command, primary=False, **kwargs):
        kwargs.setdefault("height", 38)
        icon_only = len(text) <= 2
        return ctk.CTkButton(parent, text=text, command=command, corner_radius=8,
                             fg_color=ACCENT if primary else FIELD,
                             hover_color="#83efdb" if primary else "#30415b",
                             text_color=BG if primary else TEXT,
                             font=("Segoe UI", 21 if icon_only else 12, "bold"), **kwargs)

    def combo(self, parent, values, **kwargs):
        values = list(values)
        widget = ctk.CTkComboBox(parent, values=values, state="readonly",
                               fg_color=FIELD, border_color=FIELD, button_color=FIELD,
                               button_hover_color=BORDER, dropdown_fg_color=FIELD,
                               dropdown_hover_color=BORDER, text_color=TEXT, **kwargs)
        if "variable" not in kwargs and values:
            widget.set(values[0])
        return widget

    def style_titlebar(self):
        if os.name == "nt":
            import ctypes
            try:
                hwnd = ctypes.windll.user32.GetParent(self.window.winfo_id())
                enabled = ctypes.c_int(1)
                ctypes.windll.dwmapi.DwmSetWindowAttribute(hwnd, 20, ctypes.byref(enabled), 4)
            except OSError:
                pass
        self.icon = tk.PhotoImage(width=32, height=32)
        self.icon.put(BG, to=(0, 0, 32, 32))
        for x, height in ((5, 10), (11, 21), (17, 16), (23, 25)):
            self.icon.put(ACCENT, to=(x, 29 - height, x + 4, 29))
        self.window.iconphoto(True, self.icon)

    def update_placeholder(self, event=None):
        if self.links.get("1.0", "end").strip() or self.window.focus_get() == self.links._textbox:
            self.placeholder.place_forget()
        else:
            self.placeholder.place(x=8, y=10)

    def draw_background(self):
        if not self.window.winfo_exists():
            return
        self.canvas.delete("ambient")
        width = max(self.window.winfo_width(), 960)
        height = max(self.window.winfo_height(), 640)
        t = self.frame / 30
        # A moving low-contrast spectrum, distinct from the reference's sweeping curves.
        for i in range(55):
            x = width * i / 54
            amplitude = 12 + 30 * (1 + math.sin(i * .46 + t)) + 13 * math.sin(i * .9 - t)
            self.canvas.create_line(x, height - 16, x, height - 16 - amplitude,
                                    fill="#173a42" if i % 3 else "#29233f", width=3, tags="ambient")
        for px, py, speed in self.particles:
            x = (px * width + t * 5 * speed) % width
            y = (py * height - t * 8 * speed) % height
            self.canvas.create_oval(x, y, x + 2, y + 2, fill="#355c6c", outline="", tags="ambient")
        for i in range(3):
            x = width * (.15 + i * .38) + math.sin(t * .2 + i) * 30
            y = height * .85 + math.cos(t * .25 + i) * 25
            self.canvas.create_oval(x - 120, y - 70, x + 120, y + 70,
                                    outline="#1e2440", width=1, tags="ambient")
        if self.animations.get():
            self.frame += 1
        self.animation_job = self.window.after(50 if self.animations.get() else 500, self.draw_background)

    def toggle_animation(self):
        self.animations.set(not self.animations.get())
        self.hide_menu()

    def toggle_menu(self):
        if self.menu_visible:
            self.hide_menu()
        else:
            self.menu.place(x=18, y=35, relheight=.9)
            self.menu.lift()
            self.menu_visible = True

    def hide_menu(self):
        self.menu.place_forget()
        self.menu_visible = False

    def build_settings(self):
        from ymd.gui import QUALITIES, LYRICS, PATTERNS
        panel = self.card(self.window)
        self.settings_panel = panel
        top = ctk.CTkFrame(panel, fg_color="transparent")
        top.pack(fill="x", padx=20, pady=16)
        ctk.CTkLabel(top, text="☷  Настройки", font=("Segoe UI", 22, "bold"), text_color=TEXT).pack(side="left")
        self.button(top, "×", self.close_settings, width=36).pack(side="right")
        body = ctk.CTkScrollableFrame(panel, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=12, pady=(0, 12))
        body.columnconfigure(0, weight=1)
        self.section(body, "Авторизация")
        self.token_entry = ctk.CTkEntry(body, textvariable=self.token, show="•",
                                        placeholder_text="OAuth-токен Яндекс Музыки", fg_color=FIELD,
                                        border_color=BORDER, height=38)
        self.token_entry.pack(fill="x", padx=8, pady=5)
        ctk.CTkCheckBox(body, text="Показать токен", command=self.toggle_token,
                        text_color=MUTED, fg_color=ACCENT, hover_color=BORDER).pack(anchor="w", padx=8, pady=8)
        ctk.CTkLabel(body, text="Токен хранится только в памяти", text_color=MUTED).pack(anchor="w", padx=8)
        self.section(body, "Общие")
        self.setting(body, "Качество", "quality", QUALITIES)
        self.switch(body, "Пропускать скачанные файлы", "skip_existing")
        self.switch(body, "Встроить обложку", "embed_cover")
        self.setting(body, "Размер обложки", "cover", ("400", "800", "1000", "original"), True)
        row = ctk.CTkFrame(body, fg_color=FIELD)
        row.pack(fill="x", padx=8, pady=5)
        ctk.CTkSwitch(row, text="Анимация фона", variable=self.animations, progress_color=ACCENT,
                      button_color=TEXT, text_color=TEXT).pack(anchor="w", padx=12, pady=12)
        self.section(body, "Тексты с таймкодами")
        self.setting(body, "Сохранение текста", "lyrics", LYRICS)
        ctk.CTkLabel(body, text="NetEase → LRCLIB → QQ Music → KuGou\n"
                     "До 3 сек. на источник, до 8 сек. на песню.\n"
                     "Нет LRC — музыка сохраняется без текста.",
                     justify="left", text_color=MUTED).pack(anchor="w", padx=10, pady=8)
        self.section(body, "Правила файлов")
        self.setting(body, "Имя и подпапки", "pattern", PATTERNS, True)
        ctk.CTkLabel(body, text="#title · #track-artist · #album-artist · #album\n"
                     "#year · #number · #number-padded\n#track-id · #album-id · #artist-id",
                     text_color=MUTED, justify="left").pack(anchor="w", padx=10)
        self.switch(body, "Только музыкальные альбомы", "only_music")
        self.switch(body, "Исполнитель указан первым", "stick_to_artist")
        self.switch(body, "Сохранять больше символов в именах", "unsafe_path")
        self.section(body, "Наборы правил")
        self.profile_combo = self.combo(body, list(self.profiles) or ["Мои настройки"], variable=self.profile)
        self.profile_combo.configure(state="normal")
        self.profile_combo.pack(fill="x", padx=8, pady=5)
        row = ctk.CTkFrame(body, fg_color="transparent")
        row.pack(fill="x", padx=8, pady=6)
        self.button(row, "Применить", self.apply_profile, width=120).pack(side="left")
        self.button(row, "Сохранить набор", self.save_profile, width=145).pack(side="right")
        self.section(body, "Сеть")
        for label, key in (("Пауза между треками, сек.", "delay"),
                           ("Таймаут аудиозапроса, сек.", "timeout"),
                           ("Повторы аудиозапроса (0 = ∞)", "tries"),
                           ("Пауза повтора, сек.", "retry_delay")):
            self.setting(body, label, key)
        self.setting(body, "Совместимость M4A", "compatibility", ("0", "1"))
        self.button(body, "Сохранить и закрыть", self.commit_settings, primary=True).pack(fill="x", padx=8, pady=16)

    def section(self, parent, title):
        ctk.CTkLabel(parent, text=title, font=("Segoe UI", 14, "bold"),
                     text_color=ACCENT).pack(anchor="w", padx=8, pady=(16, 6))

    def setting(self, parent, label, key, choices=None, editable=False):
        ctk.CTkLabel(parent, text=label, text_color=MUTED).pack(anchor="w", padx=8)
        if choices:
            widget = self.combo(parent, list(choices), variable=self.variables[key])
            if editable:
                widget.configure(state="normal")
        else:
            widget = ctk.CTkEntry(parent, textvariable=self.variables[key], fg_color=FIELD,
                                 border_color=BORDER, height=34)
        widget.pack(fill="x", padx=8, pady=(0, 8))

    def switch(self, parent, text, key):
        ctk.CTkSwitch(parent, text=text, variable=self.variables[key], text_color=TEXT,
                      progress_color=ACCENT, button_color=TEXT).pack(anchor="w", padx=8, pady=10)

    def open_settings(self):
        self.hide_menu()
        tk.Place.place_configure(self.settings_panel, relx=.5, rely=.5, anchor="center", width=480, relheight=.9)
        self.settings_panel.lift()

    def close_settings(self):
        if self.settings_panel:
            self.settings_panel.place_forget()
        self.hide_menu()

    def commit_settings(self):
        from ymd.gui import build_arguments
        try:
            build_arguments(self.values())
            self.save_settings()
            self.close_settings()
        except (OSError, ValueError) as error:
            messagebox.showerror("Настройки", str(error), parent=self.window)

    def show_tab(self, name):
        self.history_page.pack_forget()
        self.log_page.pack_forget()
        page = self.history_page if name == "history" else self.log_page
        page.pack(fill="both", expand=True, padx=16, pady=(0, 16))
        self.history_button.configure(fg_color=ACCENT if name == "history" else FIELD,
                                       text_color=BG if name == "history" else TEXT)
        self.log_button.configure(fg_color=ACCENT if name == "log" else FIELD,
                                   text_color=BG if name == "log" else TEXT)

    def add_history(self, item, persist=True):
        from ymd.gui import ROOT
        from ymd.cli import contained_path
        try:
            contained_path(ROOT, Path(item["path"]))
        except (KeyError, ValueError):
            return
        self.history = [old for old in self.history if old.get("path") != item["path"]]
        self.history.insert(0, item)
        self.history = self.history[:1000]
        if persist:
            try:
                from ymd.core import write_via_temporary_file
                contained_path(ROOT, self.history_path)
                write_via_temporary_file(
                    json.dumps(self.history, ensure_ascii=False, indent=2).encode(), self.history_path,
                )
            except OSError:
                self.append_log("Не удалось сохранить историю.\n")
        self.render_history()

    def render_history(self):
        for widget in self.history_list.winfo_children():
            widget.destroy()
        term = self.search.get().strip().casefold()
        items = []
        for item in self.history:
            if self.type_filter.get() != "Все форматы" and Path(item["path"]).suffix[1:].upper() != self.type_filter.get():
                continue
            if self.lyrics_filter.get() == "Есть LRC" and not item.get("source"):
                continue
            if self.lyrics_filter.get() == "Без LRC" and item.get("source"):
                continue
            if term and term not in f"{item.get('artist', '')} {item.get('title', '')} {item.get('album', '')}".casefold():
                continue
            items.append(item)
        if not items:
            ctk.CTkLabel(self.history_list, text="Скачанные треки появятся здесь" if not self.history else "Ничего не найдено",
                         text_color=MUTED).pack(pady=125)
        for item in items[:200]:
            row = ctk.CTkFrame(self.history_list, fg_color=FIELD, corner_radius=8)
            row.pack(fill="x", pady=5)
            details = ctk.CTkFrame(row, fg_color="transparent")
            details.pack(side="left", fill="x", expand=True, padx=12, pady=10)
            ctk.CTkLabel(details, text=item.get("title", Path(item["path"]).stem),
                         text_color=TEXT, font=("Segoe UI", 13, "bold"), anchor="w").pack(anchor="w")
            ctk.CTkLabel(details, text=f"{item.get('artist', '')} · {item.get('album', '')}"[:58],
                         text_color=MUTED, font=("Segoe UI", 11), anchor="w").pack(anchor="w")
            source = item.get("source")
            ctk.CTkLabel(details, text=f"LRC · {source}" if source else "Без LRC",
                         text_color=ACCENT if source else MUTED, font=("Segoe UI", 10)).pack(anchor="w")
            self.button(row, "▱", lambda p=item["path"]: self.open_history_folder(p),
                        width=32, height=32).pack(side="right", padx=8)
            self.button(row, "LRC", lambda record=item: self.refresh_lyrics(record),
                        width=42, height=32).pack(side="right")

    def refresh_lyrics(self, item):
        from ymd.gui import ROOT
        if self.running or getattr(self, "updating_lyrics", False):
            self.append_log("Дождитесь завершения текущей операции.\n")
            self.show_tab("log")
            return
        self.updating_lyrics = True
        self.status.set("Поиск LRC…")
        self.detail.configure(text=item.get("title", "")[:55])
        self.start_button.configure(state="disabled")

        def update():
            from ymd.library import update_lyrics
            try:
                result = update_lyrics(Path(item["path"]), ROOT)
                if result:
                    self.events.put(("history", {**item, "source": result.source}))
                    self.events.put(("log", f"LRC встроен: {item.get('title')} · {result.source}\n"))
                else:
                    self.events.put(("log", "LRC не найден. Исходный файл не изменён.\n"))
            except Exception as error:
                self.events.put(("log", f"Не удалось обновить LRC: {type(error).__name__}\n"))
            finally:
                self.events.put(("lyrics_done", ""))

        threading.Thread(target=update, daemon=True, name="lyrics-update").start()

    def open_history_folder(self, path):
        from ymd.cli import contained_path
        from ymd.gui import ROOT
        try:
            os.startfile(contained_path(ROOT, Path(path)).parent)
        except (OSError, ValueError) as error:
            messagebox.showerror("Папка", str(error), parent=self.window)

    def scan_library(self):
        from ymd.gui import ROOT
        from ymd.cli import contained_path
        if getattr(self, "scanning", False):
            return
        try:
            directory = contained_path(ROOT, Path(self.variables["directory"].get()))
        except ValueError:
            return
        self.scanning = True

        def scan():
            import mutagen
            from ymd.lyrics import parse_lrc
            try:
                for path in directory.rglob("*"):
                    if path.suffix.lower() not in (".mp3", ".m4a", ".flac"):
                        continue
                    try:
                        contained_path(ROOT, path)
                        audio = mutagen.File(path)
                        if audio is None or not audio.tags:
                            continue
                        def first(*keys):
                            for key in keys:
                                try:
                                    value = audio.tags.get(key)
                                except (KeyError, ValueError):
                                    continue
                                if value:
                                    return str(value[0]) if isinstance(value, list) else str(value)
                            return ""
                        has_lrc = bool(parse_lrc(first("\xa9lyr", "lyrics")))
                        if hasattr(audio.tags, "getall"):
                            has_lrc = bool(audio.tags.getall("SYLT"))
                        self.events.put(("history", {
                            "path": str(path.resolve()), "title": first("\xa9nam", "title", "TIT2") or path.stem,
                            "artist": first("\xa9ART", "artist", "TPE1"),
                            "album": first("\xa9alb", "album", "TALB"),
                            "source": "Встроенный" if has_lrc else None,
                        }))
                    except Exception:
                        continue
            finally:
                self.events.put(("scan_done", ""))

        threading.Thread(target=scan, daemon=True, name="library-scan").start()
