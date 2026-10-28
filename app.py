import queue
import re
import threading
import time
import io
import webbrowser
import json
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser
from urllib.parse import urlparse

import requests
from PIL import Image, ImageTk

from core.site_registry import load_sites, identify_site
from core.scraper import SiteScraper
from core.library import DATA_DIR, Library
from core.downloader import download_chapters
from core.translator import translate_chapters


class NovelReaderApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NovelReader2")
        self.minsize(850, 560)
        self._window_state_path = DATA_DIR / "ui_state.json"
        # Follow Windows light/dark preference by default; allow explicit overrides.
        self.theme_mode = "system"  # system, light, dark
        self.dark_mode = self._windows_prefers_dark()
        self.style = ttk.Style(self)
        self._appearance_path = DATA_DIR / "appearance_settings.json"
        self._restore_window_geometry()
        self.appearance = self._load_appearance_settings()
        self.protocol("WM_DELETE_WINDOW", self._close_app)
        self.library = Library()
        self.sites = load_sites()
        self.active_folder = None
        self.active_site = None
        self.active_chapters = []
        self.events = queue.Queue()
        self.download_stop_event = threading.Event()
        self.translate_stop_event = threading.Event()
        self.download_running = False
        self.translate_running = False
        self.download_folder = None
        self.cover_bytes_cache = {}
        self.cover_photo = None
        self.cover_request_token = 0
        self._build_ui()
        self.refresh_novels()
        self.after(150, self._poll_events)
        self.after(2000, self._check_system_theme)

    def _restore_window_geometry(self):
        """Restore the last normal window size without touching novel data."""
        import json
        from pathlib import Path

        default_geometry = "1120x760"
        geometry = default_geometry
        saved_state = "normal"
        try:
            path = Path(self._window_state_path)
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                width = int(saved.get("width", 1120))
                height = int(saved.get("height", 760))
                if width >= 850 and height >= 560:
                    geometry = f"{width}x{height}"
                if saved.get("state") == "zoomed":
                    saved_state = "zoomed"
                saved_mode = saved.get("theme_mode")
                if saved_mode in ("system", "light", "dark"):
                    self.theme_mode = saved_mode
                else:
                    # Older settings files used a manual dark_mode boolean. Prefer
                    # Windows integration when migrating from those versions.
                    self.theme_mode = "system"
                self.dark_mode = self._resolve_dark_mode()
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        self.geometry(geometry)
        if saved_state == "zoomed":
            try:
                self.state("zoomed")
            except tk.TclError:
                pass

    def _save_window_geometry(self):
        """Persist window dimensions in a separate UI settings file."""
        import json
        from pathlib import Path

        try:
            path = Path(self._window_state_path)
            path.parent.mkdir(parents=True, exist_ok=True)
            state = self.state()
            # When maximized, retain the last normal size from the existing file.
            if state == "zoomed":
                old = {}
                try:
                    old = json.loads(path.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    pass
                width = int(old.get("width", 1120))
                height = int(old.get("height", 760))
            else:
                width = max(850, int(self.winfo_width()))
                height = max(560, int(self.winfo_height()))
            path.write_text(
                json.dumps({"width": width, "height": height, "state": state, "theme_mode": self.theme_mode, "dark_mode": self.dark_mode}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )
        except (OSError, ValueError, tk.TclError):
            pass

    def _close_app(self):
        self._save_window_geometry()
        self.destroy()

    def _build_ui(self):
        self.url_var = tk.StringVar()
        self.add_btn = None

        self.status_var = tk.StringVar(value="Hazır")
        ttk.Label(self, textvariable=self.status_var, relief="sunken", anchor="w", padding=5).pack(side="bottom", fill="x")
        self.tabs = ttk.Notebook(self)
        self.tabs.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        self.download_tab = ttk.Frame(self.tabs, padding=8)
        self.novel_tab = ttk.Frame(self.tabs, padding=8)
        self.chapter_tab = ttk.Frame(self.tabs, padding=8)
        self.reader_tab = ttk.Frame(self.tabs, padding=8)
        self.filter_tab = ttk.Frame(self.tabs, padding=8)
        self.appearance_tab = ttk.Frame(self.tabs, padding=8)
        self.tabs.add(self.download_tab, text="Downloads")
        self.tabs.add(self.novel_tab, text="Novel List")
        self.tabs.add(self.chapter_tab, text="Chapters")
        self.tabs.add(self.reader_tab, text="Reader")
        self.tabs.add(self.filter_tab, text="Words Filter")
        self.tabs.add(self.appearance_tab, text="Görünüm")
        self._build_download_tab()
        self._build_novel_tab()
        self._build_chapter_tab()
        self._build_reader_tab()
        self._build_filter_tab()
        self._build_appearance_tab()
        self._apply_theme()

    def _default_appearance_settings(self):
        dark = bool(getattr(self, "dark_mode", self._windows_prefers_dark()))
        if dark:
            palette = {"background": "#242629", "panel": "#33363A", "button": "#3A3D42", "text": "#EEEEEE", "accent": "#465D78"}
        else:
            palette = {"background": "#F0F0F0", "panel": "#FFFFFF", "button": "#E6E6E6", "text": "#202020", "accent": "#C7DDF5"}
        palette.update({"font_family": "Segoe UI", "font_size": 11, "line_spacing": 4})
        return palette

    def _load_appearance_settings(self):
        from pathlib import Path
        defaults = self._default_appearance_settings()
        try:
            path = Path(self._appearance_path)
            if path.exists():
                saved = json.loads(path.read_text(encoding="utf-8"))
                for key in defaults:
                    if key in saved:
                        defaults[key] = saved[key]
        except (OSError, ValueError, TypeError, json.JSONDecodeError):
            pass
        return defaults

    def _save_appearance_settings(self):
        try:
            self._appearance_path.parent.mkdir(parents=True, exist_ok=True)
            self._appearance_path.write_text(json.dumps(self.appearance, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Ayarlar kaydedilemedi", str(exc))

    @staticmethod
    def _valid_color(value):
        value = str(value).strip()
        if not value.startswith("#"):
            value = "#" + value
        if len(value) != 7 or any(ch not in "0123456789abcdefABCDEF" for ch in value[1:]):
            raise ValueError("Renk kodu #RRGGBB biçiminde olmalı. Örn. #27374D")
        return value.upper()

    def _build_appearance_tab(self):
        intro = ttk.Label(self.appearance_tab, text="Arayüz renklerini ve okuma metnini kişiselleştirin. Değişiklikleri uygulayabilir, önizleyebilir ve sonraki açılışlar için kaydedebilirsiniz.", wraplength=900, justify="left")
        intro.pack(anchor="w", fill="x", pady=(0, 12))
        colors_frame = ttk.LabelFrame(self.appearance_tab, text="Renk ayarları", padding=10)
        colors_frame.pack(fill="x", pady=(0, 10))
        self.appearance_color_vars = {}
        color_fields = [("background", "Ana arka plan"), ("panel", "Paneller / metin alanları"), ("button", "Düğmeler"), ("text", "Yazı rengi"), ("accent", "Seçili alanlar / vurgu")]
        for row, (key, label) in enumerate(color_fields):
            ttk.Label(colors_frame, text=label).grid(row=row, column=0, sticky="w", padx=(0, 10), pady=4)
            var = tk.StringVar(value=str(self.appearance.get(key, "#FFFFFF")))
            self.appearance_color_vars[key] = var
            entry = ttk.Entry(colors_frame, textvariable=var, width=14)
            entry.grid(row=row, column=1, sticky="w", pady=4)
            entry.bind("<Return>", lambda _e: self._apply_appearance_from_controls())
            entry.bind("<FocusOut>", lambda _e: self._apply_appearance_from_controls())
            ttk.Button(colors_frame, text="Renk seç…", command=lambda k=key: self._choose_appearance_color(k)).grid(row=row, column=2, padx=8, pady=4)
        colors_frame.columnconfigure(3, weight=1)

        text_frame = ttk.LabelFrame(self.appearance_tab, text="Okuma metni", padding=10)
        text_frame.pack(fill="x", pady=(0, 10))
        ttk.Label(text_frame, text="Yazı tipi:").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        self.appearance_font_var = tk.StringVar(value=str(self.appearance.get("font_family", "Segoe UI")))
        font_combo = ttk.Combobox(text_frame, textvariable=self.appearance_font_var, values=("Segoe UI", "Arial", "Verdana", "Georgia", "Times New Roman", "Consolas"), width=22)
        font_combo.grid(row=0, column=1, sticky="w", pady=4)
        font_combo.bind("<<ComboboxSelected>>", lambda _e: self._apply_appearance_from_controls())
        ttk.Label(text_frame, text="Boyut:").grid(row=0, column=2, sticky="w", padx=(18, 8), pady=4)
        self.appearance_size_var = tk.IntVar(value=int(self.appearance.get("font_size", 11)))
        size_spin = ttk.Spinbox(text_frame, from_=9, to=32, textvariable=self.appearance_size_var, width=5, command=self._apply_appearance_from_controls)
        size_spin.grid(row=0, column=3, sticky="w", pady=4)
        size_spin.bind("<Return>", lambda _e: self._apply_appearance_from_controls())
        size_spin.bind("<FocusOut>", lambda _e: self._apply_appearance_from_controls())
        ttk.Label(text_frame, text="Satır aralığı:").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        self.appearance_spacing_var = tk.IntVar(value=int(self.appearance.get("line_spacing", 4)))
        spacing_spin = ttk.Spinbox(text_frame, from_=0, to=16, textvariable=self.appearance_spacing_var, width=5, command=self._apply_appearance_from_controls)
        spacing_spin.grid(row=1, column=1, sticky="w", pady=4)
        spacing_spin.bind("<Return>", lambda _e: self._apply_appearance_from_controls())
        spacing_spin.bind("<FocusOut>", lambda _e: self._apply_appearance_from_controls())

        preview_frame = ttk.LabelFrame(self.appearance_tab, text="Canlı önizleme", padding=8)
        preview_frame.pack(fill="both", expand=True, pady=(0, 10))
        self.appearance_preview = tk.Text(preview_frame, height=5, wrap="word", padx=10, pady=8, state="normal")
        self.appearance_preview.insert("1.0", "NovelReader2 — Okuma görünümü\nBu örnek metin, seçtiğiniz renk ve yazı ayarlarını gösterir. Değişiklikleri uyguladıkça önizleme güncellenir.")
        self.appearance_preview.configure(state="disabled")
        self.appearance_preview.pack(fill="both", expand=True)
        actions = ttk.Frame(self.appearance_tab)
        actions.pack(fill="x")
        ttk.Button(actions, text="Uygula ve kaydet", command=self._apply_appearance_from_controls).pack(side="left")
        ttk.Button(actions, text="Varsayılanlara dön", command=self._reset_appearance_settings).pack(side="left", padx=8)

    def _choose_appearance_color(self, key):
        current = self.appearance_color_vars[key].get().strip()
        try:
            current = self._valid_color(current)
        except ValueError:
            current = "#242629"
        _rgb, hex_value = colorchooser.askcolor(color=current, parent=self, title="Renk seç")
        if hex_value:
            self.appearance_color_vars[key].set(hex_value.upper())
            self._apply_appearance_from_controls()

    def _apply_appearance_from_controls(self):
        try:
            for key, var in self.appearance_color_vars.items():
                self.appearance[key] = self._valid_color(var.get())
                var.set(self.appearance[key])
            self.appearance["font_family"] = self.appearance_font_var.get().strip() or "Segoe UI"
            self.appearance["font_size"] = max(9, min(32, int(self.appearance_size_var.get())))
            self.appearance["line_spacing"] = max(0, min(16, int(self.appearance_spacing_var.get())))
        except (ValueError, tk.TclError) as exc:
            messagebox.showwarning("Geçersiz ayar", str(exc))
            return
        self._save_appearance_settings()
        self._apply_theme()
        self._apply_reader_font()
        self.status_var.set("Görünüm ayarları uygulandı ve kaydedildi.")

    def _apply_reader_font(self):
        family = str(self.appearance.get("font_family", "Segoe UI"))
        size = int(self.appearance.get("font_size", 11))
        spacing = int(self.appearance.get("line_spacing", 4))
        for name in ("reader_text", "preview_text", "filter_text", "log", "appearance_preview"):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget.configure(font=(family, size), spacing1=spacing, spacing3=spacing)
                except tk.TclError:
                    pass
        if hasattr(self, "reader_title"):
            # Keep headings visually stronger while using the chosen font family.
            try:
                self.style.configure("ReaderTitle.TLabel", font=(family, max(12, size + 1), "bold"))
            except tk.TclError:
                pass

    def _reset_appearance_settings(self):
        self.appearance = self._default_appearance_settings()
        for key, var in self.appearance_color_vars.items():
            var.set(self.appearance[key])
        self.appearance_font_var.set(self.appearance["font_family"])
        self.appearance_size_var.set(self.appearance["font_size"])
        self.appearance_spacing_var.set(self.appearance["line_spacing"])
        self._apply_appearance_from_controls()

    def _build_download_tab(self):
        url_row = ttk.Frame(self.download_tab)
        url_row.pack(fill="x", pady=(0, 8))
        ttk.Label(url_row, text="İlk bölüm adresi:").pack(side="left")
        self.url_entry = ttk.Entry(url_row, textvariable=self.url_var)
        self.url_entry.pack(side="left", fill="x", expand=True, padx=8)
        self.url_entry.bind("<Return>", lambda _e: self.add_novel())
        self._attach_paste_menu(self.url_entry)
        self.add_btn = ttk.Button(url_row, text="Romanı Ekle / Bilgileri Yenile", command=self.add_novel)
        self.add_btn.pack(side="left")
        self.theme_btn = ttk.Button(url_row, text="Koyu tema", command=self._toggle_theme)
        self.theme_btn.pack(side="right", padx=(8, 0))

        actions = ttk.Frame(self.download_tab)
        actions.pack(fill="x", pady=(0, 8))
        self.download_btn = ttk.Button(actions, text="İndirmeyi başlat", command=self.download_selected)
        self.download_btn.pack(side="left")
        ttk.Label(actions, text="Bölüm sayısı (0 = tümü):").pack(side="left", padx=(12, 3))
        self.download_limit_var = tk.StringVar(value="10")
        ttk.Entry(actions, textvariable=self.download_limit_var, width=7).pack(side="left")
        self.download_stop_btn = ttk.Button(actions, text="İndirmeyi durdur", command=self.download_stop_event.set, state="disabled")
        self.download_stop_btn.pack(side="left", padx=6)
        self.download_progress_var = tk.StringVar(value="İndirme: hazır")
        ttk.Label(actions, textvariable=self.download_progress_var).pack(side="left", padx=6)
        ttk.Button(actions, text="Listeyi yenile", command=self.refresh_novels).pack(side="left")

        split = ttk.Panedwindow(self.download_tab, orient="vertical")
        split.pack(fill="both", expand=True)
        novel_frame = ttk.LabelFrame(split, text="Roman listesi — indirmek için bir roman seçin", padding=5)
        log_frame = ttk.LabelFrame(split, text="İndirme günlüğü", padding=5)
        split.add(novel_frame, weight=2)
        split.add(log_frame, weight=3)

        self.download_tree = ttk.Treeview(novel_frame, columns=("site", "total", "downloaded", "status"), show="tree headings")
        self.download_tree.heading("#0", text="Roman")
        self.download_tree.heading("site", text="Site")
        self.download_tree.heading("total", text="Sitedeki bölüm")
        self.download_tree.heading("downloaded", text="İndirilen")
        self.download_tree.heading("status", text="Durum")
        self.download_tree.column("#0", width=430, minwidth=180, stretch=False)
        self.download_tree.column("site", width=140, minwidth=90, anchor="center", stretch=False)
        self.download_tree.column("total", width=120, minwidth=90, anchor="center", stretch=False)
        self.download_tree.column("downloaded", width=100, minwidth=80, anchor="center", stretch=False)
        self.download_tree.column("status", width=105, minwidth=85, anchor="center", stretch=False)
        self.download_tree.grid(row=0, column=0, sticky="nsew")
        download_y = ttk.Scrollbar(novel_frame, orient="vertical", command=self.download_tree.yview)
        download_x = ttk.Scrollbar(novel_frame, orient="horizontal", command=self.download_tree.xview)
        self.download_tree.configure(yscrollcommand=download_y.set, xscrollcommand=download_x.set)
        download_y.grid(row=0, column=1, sticky="ns")
        download_x.grid(row=1, column=0, sticky="ew")
        novel_frame.rowconfigure(0, weight=1)
        novel_frame.columnconfigure(0, weight=1)
        self.download_tree.bind("<<TreeviewSelect>>", lambda _e: self._select_download_novel())
        self.download_tree.bind("<Double-1>", lambda _e: self.download_selected())

        log_inner = ttk.Frame(log_frame)
        log_inner.pack(fill="both", expand=True)
        self.log = tk.Text(log_inner, wrap="word", height=10, state="disabled")
        log_y = ttk.Scrollbar(log_inner, orient="vertical", command=self.log.yview)
        self.log.configure(yscrollcommand=log_y.set)
        self.log.pack(side="left", fill="both", expand=True)
        log_y.pack(side="right", fill="y")

    def _build_novel_tab(self):
        bar = ttk.Frame(self.novel_tab)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Yenile", command=self.refresh_novels).pack(side="left")
        ttk.Button(bar, text="Bölümleri Aç", command=self.show_selected_chapters).pack(side="left", padx=6)
        ttk.Button(bar, text="Seçili romanı sil…", command=self.delete_selected_novel).pack(side="left", padx=6)
        ttk.Label(bar, text="Çeviri için yukarıdaki listeden roman seçin.").pack(side="left", padx=(12, 3))
        ttk.Label(bar, text="Bölüm sayısı (0 = tümü):").pack(side="left", padx=(8, 3))
        self.translate_limit_var = tk.StringVar(value="10")
        ttk.Entry(bar, textvariable=self.translate_limit_var, width=6).pack(side="left")
        self.translate_btn = ttk.Button(bar, text="Çeviriyi başlat", command=self.translate_selected)
        self.translate_btn.pack(side="left", padx=4)
        self.translate_stop_btn = ttk.Button(bar, text="Çeviriyi durdur", command=self.translate_stop_event.set, state="disabled")
        self.translate_stop_btn.pack(side="left", padx=2)
        self.translate_progress_var = tk.StringVar(value="Çeviri: hazır")
        ttk.Label(bar, textvariable=self.translate_progress_var).pack(side="left", padx=5)
        retry_bar = ttk.Frame(self.novel_tab)
        retry_bar.pack(fill="x", pady=(0, 8))
        self.translate_missing_btn = ttk.Button(retry_bar, text="Eksik Bölümleri Çevir", command=self.translate_missing)
        self.translate_missing_btn.pack(side="left")
        self.fallback_original_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(retry_bar, text="3 deneme başarısızsa orijinali yedekle ve devam et", variable=self.fallback_original_var).pack(side="left", padx=8)
        body = ttk.Panedwindow(self.novel_tab, orient="horizontal")
        body.pack(fill="both", expand=True)
        list_frame = ttk.LabelFrame(body, text="Romanlar", padding=5)
        preview_frame = ttk.LabelFrame(body, text="Roman ön izlemesi", padding=8)
        body.add(list_frame, weight=3)
        body.add(preview_frame, weight=2)

        self.novel_tree = ttk.Treeview(list_frame, columns=("total", "downloaded", "translated", "author", "status", "site"), show="tree headings")
        self.novel_tree.heading("#0", text="Roman")
        self.novel_tree.heading("total", text="Sitedeki bölüm")
        self.novel_tree.heading("downloaded", text="İndirilen")
        self.novel_tree.heading("translated", text="Çevrilen")
        self.novel_tree.heading("author", text="Yazar")
        self.novel_tree.heading("status", text="Yayın durumu")
        self.novel_tree.heading("site", text="Site")
        # Disable automatic stretching so user-adjusted widths remain stable.
        self.novel_tree.column("#0", width=260, minwidth=150, stretch=False)
        self.novel_tree.column("total", width=95, minwidth=70, anchor="center", stretch=False)
        self.novel_tree.column("downloaded", width=75, minwidth=60, anchor="center", stretch=False)
        self.novel_tree.column("translated", width=75, minwidth=60, anchor="center", stretch=False)
        self.novel_tree.column("author", width=130, minwidth=90, stretch=False)
        self.novel_tree.column("status", width=110, minwidth=90, anchor="center", stretch=False)
        self.novel_tree.column("site", width=105, minwidth=80, stretch=False)
        self.novel_tree.grid(row=0, column=0, sticky="nsew")
        novel_y = ttk.Scrollbar(list_frame, orient="vertical", command=self.novel_tree.yview)
        novel_x = ttk.Scrollbar(list_frame, orient="horizontal", command=self.novel_tree.xview)
        self.novel_tree.configure(yscrollcommand=novel_y.set, xscrollcommand=novel_x.set)
        novel_y.grid(row=0, column=1, sticky="ns")
        novel_x.grid(row=1, column=0, sticky="ew")
        list_frame.rowconfigure(0, weight=1)
        list_frame.columnconfigure(0, weight=1)

        total_row = ttk.Frame(preview_frame)
        total_row.pack(fill="x", pady=(0, 6))
        ttk.Label(total_row, text="Toplam bölüm:").pack(side="left")
        self.manual_total_var = tk.StringVar()
        self.manual_total_entry = ttk.Entry(total_row, textvariable=self.manual_total_var, width=8)
        self.manual_total_entry.pack(side="left", padx=5)
        self.publication_completed_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(
            total_row,
            text="Bitti (işaretli) / Devam ediyor",
            variable=self.publication_completed_var,
        ).pack(side="left", padx=(5, 4))
        ttk.Button(total_row, text="Kaydet", command=self.save_manual_total).pack(side="left")
        self.preview_title = tk.StringVar(value="Soldan bir roman seçin")
        ttk.Label(preview_frame, textvariable=self.preview_title, font=("Segoe UI", 12, "bold"), wraplength=330).pack(anchor="w", fill="x", pady=(0, 8))
        self.cover_label = ttk.Label(preview_frame, text="", anchor="center")
        self.cover_label.pack(fill="x", pady=(0, 8))
        self.preview_text = tk.Text(preview_frame, wrap="word", height=18, state="disabled", padx=8, pady=8)
        preview_y = ttk.Scrollbar(preview_frame, orient="vertical", command=self.preview_text.yview)
        self.preview_text.configure(yscrollcommand=preview_y.set)
        preview_y.pack(side="right", fill="y")
        self.preview_text.pack(side="left", fill="both", expand=True)
        self.novel_tree.bind("<<TreeviewSelect>>", lambda _e: self._select_novel())
        self.novel_tree.bind("<Double-1>", self.open_novel_for_reading)

    def _build_chapter_tab(self):
        bar = ttk.Frame(self.chapter_tab)
        bar.pack(fill="x", pady=(0, 8))
        ttk.Button(bar, text="Orijinali oku", command=self.read_selected_original).pack(side="left")
        ttk.Button(bar, text="Eksik bölümleri indir", command=self.download_selected).pack(side="left", padx=6)
        ttk.Button(bar, text="Çeviriyi oku", command=self.read_selected_translation).pack(side="left", padx=6)

        # The Treeview must be created with the frame that actually contains it.
        # Using grid(in_=...) with a widget whose parent is another frame can leave it invisible.
        chapter_tree_frame = ttk.Frame(self.chapter_tab)
        chapter_tree_frame.pack(fill="both", expand=True)
        self.chapter_tree = ttk.Treeview(chapter_tree_frame, columns=("state",), show="tree headings")
        self.chapter_tree.heading("#0", text="Bölüm adı")
        self.chapter_tree.heading("state", text="Durum")
        self.chapter_tree.column("#0", width=700, minwidth=260, stretch=True)
        self.chapter_tree.column("state", width=140, anchor="center", stretch=False)
        self.chapter_tree.grid(row=0, column=0, sticky="nsew")
        chapter_y = ttk.Scrollbar(chapter_tree_frame, orient="vertical", command=self.chapter_tree.yview)
        chapter_x = ttk.Scrollbar(chapter_tree_frame, orient="horizontal", command=self.chapter_tree.xview)
        self.chapter_tree.configure(yscrollcommand=chapter_y.set, xscrollcommand=chapter_x.set)
        chapter_y.grid(row=0, column=1, sticky="ns")
        chapter_x.grid(row=1, column=0, sticky="ew")
        chapter_tree_frame.rowconfigure(0, weight=1)
        chapter_tree_frame.columnconfigure(0, weight=1)
        self.chapter_tree.bind("<Double-1>", lambda _e: self.read_selected_chapter())

    def _build_filter_tab(self):
        """Edit literal advertising words/phrases independently for each site."""
        intro = ttk.Label(
            self.filter_tab,
            text=("Siteye özel reklam kelimeleri/cümleleri. Her satıra bir ifade yazın. "
                  "Eşleşme büyük-küçük harf duyarsızdır ve ifade metnin içinde de silinir. "
                  "Kurallar indirme sırasında ve çeviri öncesinde uygulanır."),
            wraplength=900, justify="left")
        intro.pack(anchor="w", fill="x", pady=(0, 10))
        row = ttk.Frame(self.filter_tab)
        row.pack(fill="x", pady=(0, 8))
        ttk.Label(row, text="Site:").pack(side="left")
        self.filter_site_var = tk.StringVar()
        labels = [f"{site.get('name', site['id'])} [{site['id']}]" for site in self.sites]
        self.filter_site_combo = ttk.Combobox(row, textvariable=self.filter_site_var, values=labels, state="readonly", width=35)
        self.filter_site_combo.pack(side="left", padx=8)
        self.filter_site_by_label = {f"{site.get('name', site['id'])} [{site['id']}]": site for site in self.sites}
        self.filter_site_combo.bind("<<ComboboxSelected>>", lambda _e: self._load_site_word_filters())
        ttk.Button(row, text="Kaydet", command=self._save_site_word_filters).pack(side="left", padx=4)
        ttk.Button(row, text="Listeyi temizle", command=lambda: self.filter_text.delete("1.0", "end")).pack(side="left", padx=4)
        self.filter_text = tk.Text(self.filter_tab, wrap="word", height=20, undo=True)
        self.filter_text.pack(fill="both", expand=True)
        ttk.Label(self.filter_tab, text="Not: Yalnızca eklediğiniz tam ifadeler silinir; regex kullanılmaz. Örn. 'Read more at example.com'.", wraplength=900).pack(anchor="w", pady=(8, 0))
        if labels:
            self.filter_site_combo.current(0)
            self._load_site_word_filters()

    def _load_site_word_filters(self):
        site = self.filter_site_by_label.get(self.filter_site_var.get())
        if not site:
            return
        cleanup = site.get("content_cleanup", {})
        phrases = cleanup.get("remove_phrases", [])
        self.filter_text.delete("1.0", "end")
        self.filter_text.insert("1.0", "\n".join(str(x) for x in phrases))

    def _save_site_word_filters(self):
        site = self.filter_site_by_label.get(self.filter_site_var.get())
        if not site:
            messagebox.showinfo("Site seçilmedi", "Önce bir site seçin.")
            return
        phrases = []
        seen = set()
        for line in self.filter_text.get("1.0", "end").splitlines():
            phrase = line.strip()
            if phrase and phrase.casefold() not in seen:
                phrases.append(phrase)
                seen.add(phrase.casefold())
        try:
            config_path = site.get("config_path")
            if not config_path:
                raise ValueError("Site yapılandırma dosyasının yolu bulunamadı.")
            import json
            from pathlib import Path
            path = Path(config_path)
            config = json.loads(path.read_text(encoding="utf-8"))
            cleanup = config.setdefault("content_cleanup", {})
            cleanup["remove_phrases"] = phrases
            path.write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            site["content_cleanup"] = cleanup
            self.status_var.set(f"Words Filter kaydedildi: {site.get('name', site['id'])} — {len(phrases)} ifade")
            messagebox.showinfo("Kaydedildi", f"{len(phrases)} ifade kaydedildi. Yeni indirmelerde ve çeviri öncesinde uygulanacak.")
        except Exception as exc:
            messagebox.showerror("Kaydetme hatası", str(exc))

    def _build_reader_tab(self):
        self.reader_title = tk.StringVar(value="Okumak için bir bölüm seçin")
        ttk.Label(self.reader_tab, textvariable=self.reader_title, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0, 8))
        # Pack the fixed navigation bar BEFORE the expanding text widget. If the
        # text widget is packed first, Tk can place the buttons in a side strip.
        nav = ttk.Frame(self.reader_tab)
        nav.pack(side="bottom", fill="x", pady=(8, 0))
        self.prev_chapter_btn = ttk.Button(nav, text="← Önceki", command=lambda: self.navigate_chapter(-1))
        self.prev_chapter_btn.pack(side="left")
        self.reader_status_var = tk.StringVar(value="Çeviri varsa Türkçe metin gösterilir")
        ttk.Label(nav, textvariable=self.reader_status_var, anchor="center").pack(side="left", fill="x", expand=True, padx=8)
        self.next_chapter_btn = ttk.Button(nav, text="Sonraki →", command=lambda: self.navigate_chapter(1))
        self.next_chapter_btn.pack(side="right")

        reader_area = ttk.Frame(self.reader_tab)
        reader_area.pack(side="top", fill="both", expand=True)
        self.reader_text = tk.Text(reader_area, wrap="word", font=("Segoe UI", 11), padx=14, pady=12)
        yscroll = ttk.Scrollbar(reader_area, orient="vertical", command=self.reader_text.yview)
        self.reader_text.configure(yscrollcommand=yscroll.set)
        yscroll.pack(side="right", fill="y")
        self.reader_text.pack(side="left", fill="both", expand=True)
        self.reader_text.bind("<Left>", lambda _e: self._reader_key_navigate(-1))
        self.reader_text.bind("<Right>", lambda _e: self._reader_key_navigate(1))
        self.reader_tab.bind_all("<Left>", lambda _e: self._reader_key_navigate(-1), add="+")
        self.reader_tab.bind_all("<Right>", lambda _e: self._reader_key_navigate(1), add="+")

    def _attach_paste_menu(self, widget):
        menu = tk.Menu(widget, tearoff=0)
        menu.add_command(label="Kes", command=lambda: widget.event_generate("<<Cut>>"))
        menu.add_command(label="Kopyala", command=lambda: widget.event_generate("<<Copy>>"))
        menu.add_command(label="Yapıştır", command=lambda: widget.event_generate("<<Paste>>"))
        menu.add_separator()
        menu.add_command(label="Tümünü seç", command=lambda: (widget.select_range(0, "end") if hasattr(widget, "select_range") else widget.event_generate("<<SelectAll>>")))
        def popup(event):
            try:
                widget.focus_set()
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()
        widget.bind("<Button-3>", popup)
        widget.bind("<Shift-F10>", lambda event: popup(event))

    @staticmethod
    def _windows_prefers_dark():
        """Read Windows' app theme preference; fall back to light on other OSes."""
        try:
            import winreg
            key_path = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, key_path) as key:
                value, _kind = winreg.QueryValueEx(key, "AppsUseLightTheme")
            return int(value) == 0
        except (ImportError, OSError, ValueError, TypeError):
            return False

    def _resolve_dark_mode(self):
        if self.theme_mode == "dark":
            return True
        if self.theme_mode == "light":
            return False
        return self._windows_prefers_dark()

    def _toggle_theme(self):
        # Cycle through automatic Windows matching and explicit overrides.
        self.theme_mode = {"system": "light", "light": "dark", "dark": "system"}[self.theme_mode]
        self.dark_mode = self._resolve_dark_mode()
        self._apply_theme()
        self._save_window_geometry()

    def _check_system_theme(self):
        if self.winfo_exists():
            if self.theme_mode == "system":
                detected = self._resolve_dark_mode()
                if detected != self.dark_mode:
                    self.dark_mode = detected
                    self._apply_theme()
            self.after(2000, self._check_system_theme)

    def _apply_theme(self):
        dark = bool(self.dark_mode)
        try:
            self.style.theme_use("clam")
        except tk.TclError:
            pass
        # NovelReader2 v1.5 palette restored for dark mode.
        # Keep the existing light palette and Windows theme detection.
        if dark:
            bg = "#242629"
            fg = "#eeeeee"
            field = "#33363a"
            button_bg = "#3a3d42"
            tab_bg = "#34373b"
            active_bg = "#50555b"
            select_bg = "#465d78"
            border = "#3a3d42"
            selected_fg = "#ffffff"
        else:
            bg = "#f0f0f0"
            fg = "#202020"
            field = "#ffffff"
            button_bg = "#e6e6e6"
            tab_bg = "#e2e2e2"
            active_bg = "#d6d6d6"
            select_bg = "#c7ddf5"
            border = "#d0d0d0"
            selected_fg = "#111111"
        # User-defined palette overrides the built-in v1.5 light/dark palette.
        custom = getattr(self, "appearance", {})
        bg = custom.get("background", bg)
        field = custom.get("panel", field)
        button_bg = custom.get("button", button_bg)
        fg = custom.get("text", fg)
        select_bg = custom.get("accent", select_bg)
        active_bg = select_bg
        border = button_bg
        selected_fg = fg
        self.configure(background=bg)
        self.style.configure(".", background=bg, foreground=fg)
        self.style.configure("TFrame", background=bg)
        self.style.configure("TLabel", background=bg, foreground=fg)
        self.style.configure("TButton", background=button_bg, foreground=fg, bordercolor=border)
        self.style.map("TButton", background=[("active", active_bg), ("pressed", active_bg)])
        self.style.configure("TEntry", fieldbackground=field, foreground=fg, insertcolor=fg)
        self.style.configure("TCombobox", fieldbackground=field, foreground=fg, background=button_bg, arrowcolor=fg)
        self.style.map("TCombobox", fieldbackground=[("readonly", field)], foreground=[("readonly", fg)])
        self.style.configure("TNotebook", background=bg, borderwidth=0)
        self.style.configure("TNotebook.Tab", background=tab_bg, foreground=fg, padding=(8, 4))
        self.style.map("TNotebook.Tab", background=[("selected", field), ("active", active_bg)])
        self.style.configure("TLabelframe", background=bg, foreground=fg)
        self.style.configure("TLabelframe.Label", background=bg, foreground=fg)
        self.style.configure("Treeview", background=field, fieldbackground=field, foreground=fg, rowheight=24)
        self.style.map("Treeview", background=[("selected", select_bg)], foreground=[("selected", selected_fg)])
        text_bg = field
        for name in ("log", "preview_text", "filter_text", "reader_text", "appearance_preview"):
            widget = getattr(self, name, None)
            if widget is not None:
                try:
                    widget.configure(background=text_bg, foreground=fg, insertbackground=fg, selectbackground=select_bg)
                except tk.TclError:
                    pass
        if getattr(self, "theme_btn", None):
            mode_label = {"system": "Windows", "light": "Açık", "dark": "Koyu"}[self.theme_mode]
            self.theme_btn.configure(text=f"Tema: {mode_label}")
        self._apply_reader_font()

    def _write_log(self, text):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def add_novel(self):
        url = self.url_var.get().strip()
        if not url:
            messagebox.showinfo("Adres gerekli", "İlk bölümün adresini girin. İsterseniz roman ana sayfasını da girebilirsiniz.")
            return
        if not urlparse(url).scheme:
            url = "https://" + url
            self.url_var.set(url)
        try:
            site = identify_site(url, self.sites)
        except ValueError as exc:
            messagebox.showerror("Desteklenmeyen site", str(exc))
            return
        self.add_btn.configure(state="disabled")
        self.status_var.set(f"{site['name']} roman bilgileri alınıyor; bölüm zinciri başlangıç adresinden taranıyor…")
        self._write_log(f"[TARAMA] {url}")
        def worker():
            try:
                scraper = SiteScraper(site)
                metadata, chapters = scraper.fetch_novel(url)
                folder = self.library.add_or_update_novel(metadata, chapters)
                self.events.put(("novel_added", {"site": site, "metadata": metadata, "chapters": chapters, "folder": folder.name}))
            except Exception as exc:
                self.events.put(("error", f"Roman eklenemedi: {exc}"))
        threading.Thread(target=worker, daemon=True).start()

    def refresh_novels(self):
        selected_novel = self.novel_tree.selection()[0] if self.novel_tree.selection() else self.active_folder
        selected_download = self.download_tree.selection()[0] if self.download_tree.selection() else self.active_folder
        # Normalize legacy chapter records before showing summary counts. This repairs
        # stale doubled counts as soon as the library is refreshed, not only after
        # the user opens an individual novel's Chapters tab.
        for entry in self.library.list_novels():
            folder_name = entry.get("folder")
            if folder_name:
                try:
                    self.library.get_chapters(folder_name)
                except Exception as exc:
                    self._write_log(f"[UYARI] {entry.get('title', folder_name)} kayıtları yenilenemedi: {exc}")
        novels = self.library.list_novels()
        for tree in (self.novel_tree, self.download_tree):
            for item in tree.get_children():
                tree.delete(item)
        for novel in novels:
            folder = novel.get("folder")
            title = novel.get("title") or "İsimsiz roman"
            site_name = novel.get("site_name") or novel.get("site_id", "")
            total = novel.get("site_chapter_count", 0)
            downloaded = novel.get("downloaded_chapter_count", 0)
            translated = novel.get("translated_chapter_count", 0)
            status_labels = {"completed": "Tamamlandı", "ongoing": "Devam ediyor", "hiatus": "Ara verdi", "dropped": "Bırakıldı", "unknown": "Bilinmiyor"}
            publication_status = status_labels.get(novel.get("publication_status", "unknown"), "Bilinmiyor")
            self.novel_tree.insert("", "end", iid=folder, text=title, values=(total, downloaded, translated, novel.get("author", ""), publication_status, site_name))
            self.download_tree.insert("", "end", iid=folder, text=title, values=(site_name, total, downloaded, publication_status))
        if selected_novel and self.novel_tree.exists(selected_novel):
            self.novel_tree.selection_set(selected_novel)
            self.novel_tree.focus(selected_novel)
        if selected_download and self.download_tree.exists(selected_download):
            self.download_tree.selection_set(selected_download)
            self.download_tree.focus(selected_download)
        self.status_var.set(f"Kütüphane: {len(novels)} roman")

    def _selected_folder(self):
        if self.tabs.select() == str(self.download_tab):
            selection = self.download_tree.selection()
        else:
            selection = self.novel_tree.selection()
        return selection[0] if selection else self.active_folder

    def _select_download_novel(self):
        selection = self.download_tree.selection()
        if not selection:
            return
        folder = selection[0]
        self.active_folder = folder
        if self.novel_tree.exists(folder):
            self.novel_tree.selection_set(folder)
        metadata = self.library.get_metadata(folder)
        self.active_site = next((s for s in self.sites if s["id"] == metadata.get("site_id")), None)
        self.active_chapters = self.library.get_chapters(folder)
        self._populate_chapters()
        self._update_novel_preview(metadata, folder)
        self.status_var.set(f"Seçildi: {metadata.get('title') or folder}")

    def _select_novel(self):
        selection = self.novel_tree.selection()
        folder = selection[0] if selection else self.active_folder
        if not folder:
            return
        self.active_folder = folder
        metadata = self.library.get_metadata(folder)
        self.active_site = next((s for s in self.sites if s["id"] == metadata.get("site_id")), None)
        self.active_chapters = self.library.get_chapters(folder)
        self._populate_chapters()
        self._update_novel_preview(metadata, folder)

    def _update_novel_preview(self, metadata, folder):
        self._load_cover_preview(metadata.get("cover_url") or "", folder)
        title = metadata.get("title") or folder
        self.preview_title.set(title)
        genres = metadata.get("genres") or []
        if isinstance(genres, str):
            genres = [genres]
        total = metadata.get("site_chapter_count", "Bilinmiyor")
        self.manual_total_var.set(str(total if total is not None else ""))
        self.publication_completed_var.set(metadata.get("publication_status") == "completed")
        downloaded = sum(1 for ch in self.active_chapters if ch.get("downloaded"))
        translated = sum(1 for ch in self.active_chapters if ch.get("translated"))
        description = metadata.get("description") or "Özet bilgisi bulunamadı."
        status_labels = {"completed": "Tamamlandı", "ongoing": "Devam ediyor", "hiatus": "Ara verdi", "dropped": "Bırakıldı", "unknown": "Bilinmiyor"}
        publication_status = status_labels.get(metadata.get("publication_status", "unknown"), "Bilinmiyor")
        lines = [
            f"Site: {metadata.get('site_name') or metadata.get('site_id', 'Bilinmiyor')}",
            f"Yazar: {metadata.get('author') or 'Bilinmiyor'}",
            f"Türler: {', '.join(str(g) for g in genres) if genres else 'Bilinmiyor'}",
            f"Sitedeki bölüm sayısı: {total}",
            f"Yayın durumu: {publication_status}",
            f"Durum metni: {metadata.get('publication_status_text') or 'Sayfada bulunamadı'}",
            (f"Başlangıç bölüm adresi: Hazır" if any(site.get("id") == metadata.get("site_id") and site.get("chapter_discovery", {}).get("strategy") == "next_chain" for site in self.sites)
             else f"Bulunan bölüm bağlantısı: {len([c for c in self.active_chapters if not c.get('is_info_page')])}"),
            f"İndirilen bölüm: {downloaded}",
            f"Türkçeye çevrilen bölüm: {translated}",
            f"Kapak adresi: {metadata.get('cover_url') or 'Bulunamadı'}",
            f"Roman adresi: {metadata.get('source_url') or 'Bilinmiyor'}",
            "",
            "KONU ÖZETİ",
            description,
        ]
        preview_content = "\n".join(lines)
        info_chapter = next((ch for ch in self.active_chapters if ch.get("is_info_page") or ch.get("chapter_number") == 0), None)
        if info_chapter and info_chapter.get("translated") and info_chapter.get("translated_file"):
            translated_path = self.library.novel_dir(metadata) / info_chapter["translated_file"]
            try:
                translated_info = translated_path.read_text(encoding="utf-8").strip()
                if translated_info:
                    preview_content = translated_info
            except OSError:
                pass

        # Keep the original source URL visible and clickable even when the preview
        # body is replaced with the translated Chapter 0 text.
        source_url = str(metadata.get("source_url") or "").strip()
        if source_url.startswith(("http://", "https://")):
            source_line = f"Kaynak sayfa: {source_url}\n\n"
            preview_content = source_line + preview_content
        else:
            source_url = ""

        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", preview_content)
        self.preview_text.tag_configure("source_link", foreground="#1683d8", underline=True)
        self.preview_text.tag_bind("source_link", "<Enter>", lambda _e: self.preview_text.configure(cursor="hand2"))
        self.preview_text.tag_bind("source_link", "<Leave>", lambda _e: self.preview_text.configure(cursor=""))
        self.preview_text.tag_bind("source_link", "<Button-1>", lambda _e, url=source_url: self._open_source_url(url))
        if source_url:
            start = len("Kaynak sayfa: ")
            end = start + len(source_url)
            self.preview_text.tag_add("source_link", f"1.0 + {start} chars", f"1.0 + {end} chars")
        self.preview_text.configure(state="disabled")

    @staticmethod
    def _open_source_url(url):
        if url and url.startswith(("http://", "https://")):
            webbrowser.open(url)

    def save_manual_total(self):
        folder = self.active_folder
        raw = self.manual_total_var.get().strip()
        if not folder:
            messagebox.showinfo("Roman seçilmedi", "Önce Novel List içinden bir roman seçin.")
            return
        if not raw.isdigit():
            messagebox.showerror("Geçersiz sayı", "Toplam bölüm sayısı 0 veya pozitif bir tam sayı olmalı.")
            return
        try:
            self.library.update_site_chapter_count(folder, int(raw))
            self.library.update_manual_publication_status(
                folder, "completed" if self.publication_completed_var.get() else "ongoing"
            )
            self.refresh_novels()
            if self.novel_tree.exists(folder):
                self.novel_tree.selection_set(folder)
            self._select_novel()
            status_text = "bitti" if self.publication_completed_var.get() else "devam ediyor"
            self.status_var.set(f"Toplam bölüm sayısı ve yayın durumu kaydedildi: {raw} bölüm — {status_text}")
        except Exception as exc:
            messagebox.showerror("Kaydetme hatası", str(exc))

    def _load_cover_preview(self, cover_url, folder):
        """Load a novel cover only when online; failures leave the preview text-only."""
        self.cover_request_token += 1
        token = self.cover_request_token
        self.cover_photo = None
        self.cover_label.configure(image="", text="")
        cover_url = str(cover_url or "").strip()
        if not cover_url.startswith(("http://", "https://")):
            return
        cached = self.cover_bytes_cache.get(cover_url)
        if cached:
            self.events.put(("cover_loaded", {"token": token, "folder": folder, "url": cover_url, "content": cached}))
            return

        def worker():
            try:
                response = requests.get(cover_url, timeout=8, headers={"User-Agent": "Mozilla/5.0"})
                response.raise_for_status()
                content_type = response.headers.get("Content-Type", "").lower()
                if "image" not in content_type and not response.content.startswith((b"\x89PNG", b"\xff\xd8", b"GIF8", b"RIFF")):
                    raise ValueError("Kapak adresi resim döndürmedi")
                if len(response.content) > 12 * 1024 * 1024:
                    raise ValueError("Kapak resmi çok büyük")
                self.events.put(("cover_loaded", {"token": token, "folder": folder, "url": cover_url, "content": response.content}))
            except Exception:
                # Offline, blocked or missing cover: no placeholder or broken-image icon.
                self.events.put(("cover_failed", {"token": token, "folder": folder, "url": cover_url}))
        threading.Thread(target=worker, daemon=True, name="NovelReader-Cover").start()

    def _show_cover_preview(self, payload):
        if payload.get("token") != self.cover_request_token or payload.get("folder") != self.active_folder:
            return
        try:
            content = payload["content"]
            image = Image.open(io.BytesIO(content)).convert("RGB")
            image.thumbnail((220, 280), Image.Resampling.LANCZOS)
            self.cover_photo = ImageTk.PhotoImage(image)
            self.cover_bytes_cache[payload["url"]] = content
            self.cover_label.configure(image=self.cover_photo, text="")
        except Exception:
            self.cover_photo = None
            self.cover_label.configure(image="", text="")

    def delete_selected_novel(self):
        selection = self.novel_tree.selection()
        if not selection:
            messagebox.showinfo("Roman seçilmedi", "Silmek için önce Novel List sekmesinden bir roman seçin.")
            return
        folder = selection[0]
        metadata = self.library.get_metadata(folder)
        title = metadata.get("title") or folder
        answer = messagebox.askyesno(
            "Romanı ve dosyalarını sil?",
            f"'{title}' romanını ve indirilen tüm bölüm dosyalarını bilgisayardan silmek istediğinize emin misiniz?\n\nBu işlem geri alınamaz.",
            icon="warning"
        )
        if not answer:
            return
        try:
            self.library.delete_novel(folder)
        except Exception as exc:
            messagebox.showerror("Silinemedi", f"Roman silinemedi: {exc}")
            return
        if self.active_folder == folder:
            self.active_folder = None
            self.active_site = None
            self.active_chapters = []
            for item in self.chapter_tree.get_children():
                self.chapter_tree.delete(item)
            self.reader_title.set("Okumak için bir bölüm seçin")
            self.reader_text.delete("1.0", "end")
        self.refresh_novels()
        self.preview_title.set("Soldan bir roman seçin")
        self.preview_text.configure(state="normal")
        self.preview_text.delete("1.0", "end")
        self.preview_text.configure(state="disabled")
        self._write_log(f"[SİLİNDİ] {title} ve yerel bölüm dosyaları silindi.")
        self.status_var.set(f"Silindi: {title}")

    def show_selected_chapters(self):
        folder = self._selected_folder()
        if not folder:
            messagebox.showinfo("Roman seçilmedi", "Önce listeden bir roman seçin.")
            return
        self.active_folder = folder
        self._select_novel()
        # Always reload from disk so the chapter list cannot remain stale after
        # a download/refresh or when switching between novels.
        self.active_chapters = self.library.get_chapters(folder)
        self._populate_chapters()
        self.tabs.select(self.chapter_tab)

    def open_novel_for_reading(self, _event=None):
        """Open Chapter 0 on first read, otherwise resume the last opened chapter."""
        selection = self.novel_tree.selection()
        if not selection:
            return
        folder = selection[0]
        self.active_folder = folder
        self._select_novel()
        self.active_chapters = self.library.get_chapters(folder)
        self._populate_chapters()
        if not self.active_chapters:
            messagebox.showinfo("Bölüm bulunamadı", "Bu roman için bölüm kaydı bulunamadı. Roman bilgilerini yenilemeyi deneyin.")
            self.tabs.select(self.chapter_tab)
            return

        metadata = self.library.get_metadata(folder)
        last_id = metadata.get("last_read_chapter_id")
        last_url = metadata.get("last_read_source_url")
        chapter = next((c for c in self.active_chapters if last_id and c.get("chapter_id") == last_id), None)
        if chapter is None and last_url:
            chapter = next((c for c in self.active_chapters if c.get("source_url") == last_url), None)
        if chapter is None:
            chapter = next((c for c in self.active_chapters if c.get("is_info_page") or c.get("chapter_number") == 0), self.active_chapters[0])
        try:
            index = self.active_chapters.index(chapter)
            self.chapter_tree.selection_set(str(index))
            self.chapter_tree.focus(str(index))
            self.chapter_tree.see(str(index))
        except (ValueError, tk.TclError):
            pass
        self.read_chapter(chapter, remember=True)

    def _populate_chapters(self):
        for item in self.chapter_tree.get_children():
            self.chapter_tree.delete(item)
        if not self.active_chapters:
            self.chapter_tree.insert("", "end", iid="__empty__", text="Bölüm kaydı bulunamadı — roman bilgilerini yenileyin", values=("Boş", ""))
            return
        novel_title = self.library.get_metadata(self.active_folder).get("title", "") if self.active_folder else ""
        for index, chapter in enumerate(self.active_chapters):
            if not isinstance(chapter, dict):
                continue
            if chapter.get("translation_status") == "fallback_original":
                state = "Orijinal yedek"
            elif chapter.get("translation_status") == "failed":
                state = "Çeviri eksik"
            else:
                state = ("Çevrildi" if chapter.get("translated") else ("İndirildi" if chapter.get("downloaded") else "Bekliyor"))
            title = chapter.get("resolved_title") or chapter.get("title") or ""
            # Never expose internal hash IDs or synthetic local:// recovery URLs as titles.
            title = SiteScraper._clean_chapter_title(title, novel_title)
            if not title:
                source_url = str(chapter.get("source_url") or "")
                match = re.search(r"/chapter-(\d+)(?:\.html)?/?$", source_url, flags=re.I)
                number = match.group(1) if match else chapter.get("chapter_number", index)
                title = f"Bölüm {number}"
            self.chapter_tree.insert("", "end", iid=str(index), text=title, values=(state,))

    def _selected_chapter(self):
        selection = self.chapter_tree.selection()
        if not selection:
            return None
        try:
            return self.active_chapters[int(selection[0])]
        except (ValueError, IndexError):
            return None

    def read_selected_original(self):
        chapter = self._selected_chapter()
        if not chapter or not self.active_folder:
            messagebox.showinfo("Bölüm seçilmedi", "Önce Chapters sekmesinden bir bölüm seçin.")
            return
        if not chapter.get("downloaded") and not chapter.get("is_info_page"):
            messagebox.showinfo("Orijinal yok", "Bu bölüm henüz indirilmedi.")
            return
        self.read_chapter(chapter, remember=True, force_original=True)

    def read_selected_chapter(self):
        chapter = self._selected_chapter()
        if not chapter or not self.active_folder:
            messagebox.showinfo("Bölüm seçilmedi", "Önce bir bölüm seçin.")
            return
        self.read_chapter(chapter, remember=True)

    def read_chapter(self, chapter, remember=True, force_translation=False, force_original=False):
        title = chapter.get("resolved_title") or chapter.get("title", "Bölüm")
        translated = bool(chapter.get("translated") and chapter.get("translated_file"))
        if force_translation and not translated:
            messagebox.showinfo("Çeviri yok", "Bu bölüm henüz Türkçeye çevrilmedi.")
            return
        # Prefer Turkish by default; the explicit original button bypasses translation.
        if translated and not force_original:
            content = self.library.read_translation(self.active_folder, chapter)
            display_title = title + " — Türkçe"
            self.reader_status_var.set("Türkçe çeviri gösteriliyor")
        else:
            content = self.library.read_chapter(self.active_folder, chapter)
            display_title = title + (" — Orijinal" if force_original and translated else " — Kaynak metin (çeviri yok)")
            self.reader_status_var.set("Orijinal kaynak metin gösteriliyor" if force_original else "Bu bölümün Türkçe çevirisi henüz yok; kaynak metin gösteriliyor")
        self.reader_title.set(display_title)
        self.reader_text.delete("1.0", "end")
        self.reader_text.insert("1.0", content)
        if remember:
            try:
                self.library.save_reading_progress(self.active_folder, chapter)
            except Exception as exc:
                self._write_log(f"[UYARI] Okuma konumu kaydedilemedi: {exc}")
        self.tabs.select(self.reader_tab)
        self.reader_text.focus_set()
        self._update_reader_navigation()

    def _current_chapter_index(self):
        selected = self.chapter_tree.selection()
        if selected and selected[0].isdigit():
            index = int(selected[0])
            if 0 <= index < len(self.active_chapters):
                return index
        title = self.reader_title.get().replace(" — Türkçe", "").replace(" — Kaynak metin (çeviri yok)", "")
        for i, chapter in enumerate(self.active_chapters):
            if (chapter.get("resolved_title") or chapter.get("title", "Bölüm")) == title:
                return i
        return 0 if self.active_chapters else -1

    def _update_reader_navigation(self):
        index = self._current_chapter_index()
        readable = [i for i, c in enumerate(self.active_chapters) if c.get("downloaded") or c.get("translated") or c.get("is_info_page")]
        self.prev_chapter_btn.configure(state="normal" if any(i < index for i in readable) else "disabled")
        self.next_chapter_btn.configure(state="normal" if any(i > index for i in readable) else "disabled")

    def _reader_key_navigate(self, delta):
        if self.tabs.select() != str(self.reader_tab):
            return None
        self.navigate_chapter(delta)
        return "break"

    def navigate_chapter(self, delta):
        if not self.active_chapters or not self.active_folder:
            return
        current = self._current_chapter_index()
        candidates = [i for i, c in enumerate(self.active_chapters)
                      if c.get("downloaded") or c.get("translated") or c.get("is_info_page")]
        target = next((i for i in (candidates if delta > 0 else reversed(candidates))
                       if (i > current if delta > 0 else i < current)), None)
        if target is None:
            return
        chapter = self.active_chapters[target]
        self.chapter_tree.selection_set(str(target))
        self.chapter_tree.focus(str(target))
        self.chapter_tree.see(str(target))
        self.read_chapter(chapter, remember=True)

    @staticmethod
    def _parse_limit(value, label):
        try:
            limit = int(value.strip())
        except (AttributeError, ValueError):
            raise ValueError(f"{label} için 0 veya pozitif bir tam sayı girin.")
        if limit < 0:
            raise ValueError(f"{label} negatif olamaz. 0 tüm uygun bölümler demektir.")
        return limit

    def download_selected(self):
        selection = self.download_tree.selection()
        folder = selection[0] if selection else self.active_folder
        if not folder:
            messagebox.showinfo("Roman seçilmedi", "Downloads sekmesindeki listeden indirilecek romanı seçin.")
            return
        if self.download_running:
            messagebox.showinfo("İndirme sürüyor", "Bir indirme görevi zaten çalışıyor. Önce onu bitirin veya durdurun.")
            return
        try:
            limit = self._parse_limit(self.download_limit_var.get(), "İndirme miktarı")
        except ValueError as exc:
            messagebox.showerror("Geçersiz bölüm sayısı", str(exc)); return
        metadata = self.library.get_metadata(folder)
        site = next((s for s in self.sites if s["id"] == metadata.get("site_id")), None)
        if not site:
            messagebox.showerror("Site bulunamadı", "Bu roman için etkin site yapılandırması yok."); return
        chapters = self.library.get_chapters(folder)
        pending = [x for x in chapters if not x.get("is_info_page") and not x.get("downloaded")]
        # The downloader follows each chapter's Next link at runtime. Do not cap
        # the batch to homepage-discovered links: the list may be incomplete.
        if not pending and not any(x.get("downloaded") and x.get("source_url") and not x.get("is_info_page") for x in chapters):
            messagebox.showinfo("Başlangıç adresi eksik", "Önce ilk bölüm adresini girip roman bilgilerini yenileyin."); return
        self.active_folder = folder
        self.download_folder = folder
        self.download_stop_event.clear()
        self.download_running = True
        self.download_btn.configure(state="disabled")
        self.download_stop_btn.configure(state="normal")
        self.tabs.select(self.download_tab)
        limit_label = "tümü" if limit == 0 else str(limit)
        self._write_log(f"[İNDİRME BAŞLADI] {metadata.get('title')} — sıralı Next zinciriyle indirme (limit: {limit_label}; ana sayfadaki bölüm sayısı: {metadata.get('site_chapter_count', 'Bilinmiyor')})")
        def progress(index, total, title, state):
            self.events.put(("download_progress", {"index": index, "total": total, "title": title, "state": state, "folder": folder}))
        def worker():
            try:
                errors = download_chapters(site, folder, chapters, progress, self.download_stop_event, limit=limit)
                self.events.put(("download_done", {"errors": errors, "folder": folder, "stopped": self.download_stop_event.is_set()}))
            except Exception as exc:
                self.events.put(("download_done", {"errors": [str(exc)], "folder": folder, "stopped": self.download_stop_event.is_set()}))
        threading.Thread(target=worker, daemon=True, name="NovelReader-Download").start()

    def _selected_novel_for_translation(self):
        selection = self.novel_tree.selection()
        return selection[0] if selection else None

    def translate_selected(self):
        folder = self._selected_novel_for_translation()
        if not folder:
            messagebox.showinfo("Roman seçilmedi", "Çeviri için Novel List içinden bir roman seçin."); return
        if self.translate_running:
            messagebox.showinfo("Çeviri sürüyor", "Bir çeviri görevi zaten çalışıyor. Önce onu bitirin veya durdurun."); return
        try:
            limit = self._parse_limit(self.translate_limit_var.get(), "Çeviri miktarı")
        except ValueError as exc:
            messagebox.showerror("Geçersiz bölüm sayısı", str(exc)); return
        chapters = self.library.get_chapters(folder)
        # Normal mode resumes after the latest translated/attempted chapter. This
        # also keeps older unmarked gaps behind the cursor out of the normal queue.
        attempted_states = {"failed", "fallback_original"}
        resume_index = max((i for i, item in enumerate(chapters)
                            if item.get("translated") or item.get("translation_status") in attempted_states),
                           default=-1)
        pending = [x for i, x in enumerate(chapters) if i > resume_index and x.get("downloaded")
                   and not x.get("translated") and x.get("translation_status") not in attempted_states]
        batch = pending if limit == 0 else pending[:limit]
        if not batch:
            messagebox.showinfo("Çeviri yok", "Çevrilecek indirilmiş bölüm bulunamadı."); return
        self.translate_stop_event.clear()
        self.translate_running = True
        self.translate_btn.configure(state="disabled")
        self.translate_missing_btn.configure(state="disabled")
        self.translate_stop_btn.configure(state="normal")
        metadata = self.library.get_metadata(folder)
        fallback_original = self.fallback_original_var.get()
        limit_label = "tümü" if limit == 0 else str(limit)
        self._write_log(f"[ÇEVİRİ BAŞLADI] {metadata.get('title')} — bu turda {len(batch)} / {len(pending)} bölüm (limit: {limit_label})")
        def progress(index, total, title, state):
            self.events.put(("translate_progress", {"index": index, "total": total, "title": title, "state": state, "folder": folder}))
        def worker():
            try:
                errors = []
                if limit != 0:
                    errors = translate_chapters(folder, batch, progress, self.translate_stop_event,
                                                fallback_original=fallback_original)
                else:
                    # Unlimited mode follows the queue while a download of this same novel is still active.
                    attempted = set()
                    completed = 0
                    worker_library = Library()
                    while not self.translate_stop_event.is_set():
                        current = worker_library.get_chapters(folder)
                        attempted_states = {"failed", "fallback_original"}
                        resume_index = max((i for i, item in enumerate(current)
                                            if item.get("translated") or item.get("translation_status") in attempted_states),
                                           default=-1)
                        remaining = [x for i, x in enumerate(current) if i > resume_index and x.get("downloaded")
                                     and not x.get("translated") and x.get("translation_status") not in attempted_states
                                     and x.get("source_url") not in attempted]
                        if not remaining:
                            if self.download_running and self.download_folder == folder and not self.translate_stop_event.is_set():
                                time.sleep(0.5)
                                continue
                            break
                        chapter = remaining[0]
                        attempted.add(chapter.get("source_url"))
                        def one_progress(_index, _total, title, state):
                            progress(completed + 1, completed + len(remaining), title, state)
                        chapter_errors = translate_chapters(folder, [chapter], one_progress, self.translate_stop_event,
                                                            fallback_original=fallback_original)
                        errors.extend(chapter_errors)
                        completed += 1
                self.events.put(("translate_done", {"errors": errors, "folder": folder, "stopped": self.translate_stop_event.is_set()}))
            except Exception as exc:
                self.events.put(("translate_done", {"errors": [str(exc)], "folder": folder, "stopped": self.translate_stop_event.is_set()}))
        threading.Thread(target=worker, daemon=True, name="NovelReader-Translate").start()

    def translate_missing(self):
        """Retry only older chapters marked failed or served as original fallback."""
        folder = self._selected_novel_for_translation()
        if not folder:
            messagebox.showinfo("Roman seçilmedi", "Eksik bölümleri çevirmek için Novel List içinden roman seçin.")
            return
        if self.translate_running:
            messagebox.showinfo("Çeviri sürüyor", "Önce çalışan çeviri görevini bitirin veya durdurun.")
            return
        try:
            limit = self._parse_limit(self.translate_limit_var.get(), "Çeviri miktarı")
        except ValueError as exc:
            messagebox.showerror("Geçersiz bölüm sayısı", str(exc))
            return
        chapters = self.library.get_chapters(folder)
        missing = []
        for index, chapter in enumerate(chapters):
            if not chapter.get("downloaded"):
                continue
            state = chapter.get("translation_status")
            if state in {"failed", "fallback_original"}:
                missing.append(chapter)
                continue
            # Backward compatibility: older versions did not record failure
            # states. An untranslated chapter before a later successful translation
            # is an in-between gap; trailing chapters remain for normal continuation.
            if not chapter.get("translated") and any(
                    later.get("translated") and later.get("translation_status", "translated") == "translated"
                    for later in chapters[index + 1:]):
                missing.append(chapter)
        batch = missing if limit == 0 else missing[:limit]
        if not batch:
            messagebox.showinfo("Eksik bölüm yok", "Daha önce başarısız olmuş veya orijinali yedeklenmiş bölüm bulunamadı.")
            return
        self.translate_stop_event.clear()
        self.translate_running = True
        self.translate_btn.configure(state="disabled")
        self.translate_missing_btn.configure(state="disabled")
        self.translate_stop_btn.configure(state="normal")
        metadata = self.library.get_metadata(folder)
        fallback_original = self.fallback_original_var.get()
        self._write_log(f"[EKSİK ÇEVİRİ BAŞLADI] {metadata.get('title')} — {len(batch)} / {len(missing)} eski eksik bölüm")
        def progress(index, total, title, state):
            self.events.put(("translate_progress", {"index": index, "total": total, "title": title, "state": state, "folder": folder}))
        def worker():
            try:
                errors = translate_chapters(folder, batch, progress, self.translate_stop_event,
                                            retry_failed=True, fallback_original=fallback_original)
                self.events.put(("translate_done", {"errors": errors, "folder": folder,
                                                     "stopped": self.translate_stop_event.is_set(), "missing_retry": True}))
            except Exception as exc:
                self.events.put(("translate_done", {"errors": [str(exc)], "folder": folder,
                                                     "stopped": self.translate_stop_event.is_set(), "missing_retry": True}))
        threading.Thread(target=worker, daemon=True, name="NovelReader-Retry-Missing").start()

    def read_selected_translation(self):
        chapter = self._selected_chapter()
        if not chapter or not self.active_folder:
            messagebox.showinfo("Bölüm seçilmedi", "Önce Chapters sekmesinden bir bölüm seçin.")
            return
        if not chapter.get("translated"):
            messagebox.showinfo("Çeviri yok", "Bu bölüm henüz çevrilmedi.")
            return
        title = chapter.get("resolved_title") or chapter.get("title", "Bölüm")
        self.read_chapter(chapter, remember=True, force_translation=True)

    def _poll_events(self):
        try:
            while True:
                event, payload = self.events.get_nowait()
                if event == "error":
                    self.add_btn.configure(state="normal")
                    self.status_var.set("İşlem başarısız")
                    self._write_log("[HATA] " + payload)
                    messagebox.showerror("Hata", payload)
                elif event == "novel_added":
                    self.add_btn.configure(state="normal")
                    self.active_folder = payload["folder"]
                    self.active_site = payload["site"]
                    is_next_chain = any(site.get("id") == payload['metadata'].get("site_id") and site.get("chapter_discovery", {}).get("strategy") == "next_chain" for site in self.sites)
                    if is_next_chain:
                        self.status_var.set(f"Eklendi: {payload['metadata'].get('title')} — başlangıç bölüm adresi kaydedildi; ilk indirme bu adresten başlayacak")
                        self._write_log(f"[TAMAM] {payload['metadata'].get('title')} — sitede {payload['metadata'].get('site_chapter_count')} bölüm; ilk indirme kaydedilen başlangıç URL’sinden yapılacak, sonra Next zinciri izlenecek. Chapter 0 bilgi sayfası hazır.")
                    else:
                        self.status_var.set(f"Eklendi: {payload['metadata'].get('title')} — {len(payload['chapters'])} bölüm bağlantısı bulundu")
                        self._write_log(f"[TAMAM] {payload['metadata'].get('title')} — sitede {payload['metadata'].get('site_chapter_count')} bölüm; {len(payload['chapters'])} bağlantı bulundu")
                    warning = payload['metadata'].get('chapter_discovery_warning')
                    if warning:
                        self._write_log("[UYARI] " + warning)
                    self.refresh_novels()
                    if self.novel_tree.exists(self.active_folder):
                        self.novel_tree.selection_set(self.active_folder)
                        self._select_novel()
                        self.tabs.select(self.chapter_tab)
                elif event == "cover_loaded":
                    self._show_cover_preview(payload)
                elif event == "cover_failed":
                    # Keep the panel clean when offline or when the site has no usable cover.
                    if payload.get("token") == self.cover_request_token and payload.get("folder") == self.active_folder:
                        self.cover_photo = None
                        self.cover_label.configure(image="", text="")
                elif event == "download_progress":
                    self._write_log(f"[İNDİRME {payload['index']}/{payload['total']}] {payload['state']} — {payload['title']}")
                    self.download_progress_var.set(f"İndirme: {payload['index']}/{payload['total']} — {payload['state']}")
                    self.status_var.set(f"İndirme: {payload['index']}/{payload['total']} — {payload['state']}")
                elif event == "translate_progress":
                    self._write_log(f"[ÇEVİRİ {payload['index']}/{payload['total']}] {payload['state']} — {payload['title']}")
                    self.translate_progress_var.set(f"Çeviri: {payload['index']}/{payload['total']} — {payload['state']}")
                    self.status_var.set(f"Çeviri: {payload['index']}/{payload['total']} — {payload['state']}")
                elif event == "translate_done":
                    self.translate_running = False
                    self.translate_btn.configure(state="normal")
                    self.translate_missing_btn.configure(state="normal")
                    self.translate_stop_btn.configure(state="disabled")
                    self.translate_progress_var.set("Çeviri: durduruldu" if payload["stopped"] else "Çeviri: tamamlandı")
                    self.refresh_novels()
                    if self.active_folder == payload["folder"]:
                        self._select_novel()
                    task_label = "EKSİK ÇEVİRİ" if payload.get("missing_retry") else "ÇEVİRİ"
                    self._write_log(f"[{task_label} BİTTİ] Hata sayısı: {len(payload['errors'])}" + (" — kullanıcı durdurdu" if payload["stopped"] else ""))
                    if payload["errors"]:
                        self._write_log("İlk çeviri hatası: " + str(payload["errors"][0]))
                    self.status_var.set("Çeviri durdu" if payload["stopped"] else "Çeviri turu tamamlandı")
                elif event == "download_done":
                    self.download_running = False
                    self.download_btn.configure(state="normal")
                    self.download_stop_btn.configure(state="disabled")
                    self.download_progress_var.set("İndirme: durduruldu" if payload["stopped"] else "İndirme: tamamlandı")
                    self.refresh_novels()
                    if self.active_folder == payload["folder"]:
                        self._select_novel()
                    self._write_log(f"[BİTTİ] Hata sayısı: {len(payload['errors'])}" + (" — kullanıcı durdurdu" if payload["stopped"] else ""))
                    if payload["errors"]:
                        self._write_log("İlk hata: " + str(payload["errors"][0]))
                    self.status_var.set("İndirme durdu" if payload["stopped"] else "İndirme işlemi tamamlandı")
        except queue.Empty:
            pass
        self.after(150, self._poll_events)
        self.after(2000, self._check_system_theme)


if __name__ == "__main__":
    NovelReaderApp().mainloop()
