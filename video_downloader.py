"""
Video-Downloader – YouTube, TikTok, Instagram, X, Twitch, Reddit u.v.m.
Einfach Link(s) einfügen und auf "Download" klicken.

Basiert auf yt-dlp (https://github.com/yt-dlp/yt-dlp).
"""

import os
import sys
import json
import queue
import shutil
import zipfile
import threading
import subprocess
import webbrowser
import urllib.request
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

FROZEN = getattr(sys, "frozen", False)  # True, wenn als .exe gestartet

# In einer Fenster-.exe gibt es keine Konsole -> Ausgaben ins Leere leiten
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w", encoding="utf-8")
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w", encoding="utf-8")

REPO_URL = "https://github.com/CASHFL00W/video-downloader"
RELEASES_URL = REPO_URL + "/releases/latest"
API_LATEST = "https://api.github.com/repos/CASHFL00W/video-downloader/releases/latest"
ASSET_NAME = "VideoDownloader.exe"

try:
    from _version import VERSION  # wird beim Bauen der .exe automatisch erzeugt
except ImportError:
    VERSION = "dev"


# --------------------------------------------------------------------------
# Selbst-Update
# --------------------------------------------------------------------------
def version_tuple(v):
    try:
        return tuple(int(x) for x in v.lstrip("vV").split("."))
    except ValueError:
        return (0,)


def http_get(url, timeout=30):
    req = urllib.request.Request(url, headers={"User-Agent": "VideoDownloader",
                                               "Accept": "application/vnd.github+json"})
    return urllib.request.urlopen(req, timeout=timeout)


def check_for_update(q, manual):
    """Fragt GitHub nach der neuesten Version."""
    try:
        with http_get(API_LATEST, timeout=15) as r:
            data = json.load(r)
        latest = data.get("tag_name", "")
        asset = next((a for a in data.get("assets", []) if a.get("name") == ASSET_NAME), None)
        if asset and version_tuple(latest) > version_tuple(VERSION):
            q.put(("update_available", {
                "version": latest.lstrip("vV"),
                "url": asset["browser_download_url"],
                "size": asset.get("size", 0),
                "digest": asset.get("digest") or "",
                "notes": data.get("name", ""),
            }, manual))
        else:
            q.put(("update_none", latest.lstrip("vV"), manual))
    except Exception as e:
        q.put(("update_check_failed", str(e), manual))


def cleanup_old_exe():
    """Entfernt die alte .exe, die beim letzten Update übrig geblieben ist."""
    if FROZEN:
        old = os.path.splitext(sys.executable)[0] + ".old.exe"
        try:
            if os.path.exists(old):
                os.remove(old)
        except OSError:
            pass


def download_and_install_update(info, q):
    """Lädt die neue .exe herunter, tauscht sie gegen die laufende und startet neu."""
    exe = sys.executable
    base = os.path.splitext(exe)[0]
    new_path = base + ".new.exe"
    old_path = base + ".old.exe"
    try:
        import hashlib
        sha = hashlib.sha256()
        with http_get(info["url"], timeout=60) as r, open(new_path, "wb") as f:
            total = int(r.headers.get("Content-Length") or info.get("size") or 0)
            done = 0
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                sha.update(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    q.put(("progress", pct, f"Update wird geladen ... {pct:4.0f} %  "
                                            f"({done // 1048576} / {total // 1048576} MB)"))

        # Datei prüfen: Größe und (falls vorhanden) Prüfsumme von GitHub
        if info.get("size") and os.path.getsize(new_path) != info["size"]:
            raise RuntimeError("Download unvollständig.")
        digest = info.get("digest", "")
        if digest.startswith("sha256:") and digest[7:].lower() != sha.hexdigest():
            raise RuntimeError("Prüfsumme stimmt nicht – Update abgebrochen.")

        # Laufende .exe umbenennen (unter Windows erlaubt) und neue an ihre Stelle setzen
        if os.path.exists(old_path):
            os.remove(old_path)
        os.replace(exe, old_path)
        try:
            os.replace(new_path, exe)
        except Exception:
            os.replace(old_path, exe)  # zurückrollen
            raise

        # Neue Version starten (frische Umgebung, damit sie sauber entpackt)
        env = dict(os.environ)
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        for key in list(env):
            if key.startswith("_PYI") or key == "_MEIPASS2":
                env.pop(key, None)
        subprocess.Popen([exe], env=env, close_fds=True,
                         creationflags=getattr(subprocess, "DETACHED_PROCESS", 0))
        q.put(("update_installed", info["version"]))
    except Exception as e:
        try:
            if os.path.exists(new_path):
                os.remove(new_path)
        except OSError:
            pass
        q.put(("update_failed", str(e)))


# --------------------------------------------------------------------------
# yt-dlp laden (in der .exe bereits eingebaut)
# --------------------------------------------------------------------------
def ensure_ytdlp():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        if FROZEN:
            raise
        print("yt-dlp wird installiert ... (nur beim ersten Start)")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        )
    import yt_dlp
    return yt_dlp


yt_dlp = ensure_ytdlp()

try:
    import sv_ttk  # Windows-11-Design (Sun Valley) mit Hell/Dunkel
except ImportError:
    sv_ttk = None
    if not FROZEN:
        try:
            subprocess.check_call([sys.executable, "-m", "pip", "install", "sv-ttk"])
            import sv_ttk
        except Exception:
            sv_ttk = None


# --------------------------------------------------------------------------
# Hell / Dunkel
# --------------------------------------------------------------------------
THEMES = {"System": "system", "Hell": "light", "Dunkel": "dark"}

TEXT_COLORS = {
    "light": {"bg": "#ffffff", "fg": "#1c1c1c", "sel": "#cce4f7",
              "log_bg": "#f3f3f3", "log_fg": "#1c1c1c"},
    "dark": {"bg": "#2b2b2b", "fg": "#ececec", "sel": "#264f78",
             "log_bg": "#1c1c1c", "log_fg": "#d4d4d4"},
}


def windows_uses_dark():
    """Liest aus der Windows-Registry, ob Apps im dunklen Modus laufen sollen."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as k:
            value, _ = winreg.QueryValueEx(k, "AppsUseLightTheme")
        return value == 0
    except Exception:
        return False


def set_titlebar_dark(window, dark):
    """Färbt die Windows-Titelleiste passend ein (Windows 10/11)."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        window.update_idletasks()
        hwnd = ctypes.windll.user32.GetParent(window.winfo_id())
        value = ctypes.c_int(1 if dark else 0)
        for attr in (20, 19):  # DWMWA_USE_IMMERSIVE_DARK_MODE (neu / alt)
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attr, ctypes.byref(value), ctypes.sizeof(value)) == 0:
                break
    except Exception:
        pass


# --------------------------------------------------------------------------
# Pfade & ffmpeg
# --------------------------------------------------------------------------
def resource_path(name):
    base = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base, name)


APP_DIR = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                       "VideoDownloader")
FFMPEG_DIR = os.path.join(APP_DIR, "ffmpeg")
FFMPEG_URL = ("https://github.com/yt-dlp/FFmpeg-Builds/releases/download/latest/"
              "ffmpeg-master-latest-win64-gpl.zip")
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Video-Downloader")


def find_ffmpeg():
    """Gibt den Ordner mit ffmpeg zurück oder None."""
    exe = "ffmpeg.exe" if sys.platform == "win32" else "ffmpeg"
    if os.path.isfile(os.path.join(FFMPEG_DIR, exe)):
        return FFMPEG_DIR
    found = shutil.which("ffmpeg")
    return os.path.dirname(found) if found else None


def install_ffmpeg(q):
    """Lädt ffmpeg (einmalig) herunter und entpackt ffmpeg.exe + ffprobe.exe."""
    os.makedirs(FFMPEG_DIR, exist_ok=True)
    zip_path = os.path.join(APP_DIR, "ffmpeg.zip")
    try:
        with urllib.request.urlopen(FFMPEG_URL, timeout=60) as r, open(zip_path, "wb") as f:
            total = int(r.headers.get("Content-Length") or 0)
            done = 0
            while True:
                chunk = r.read(1024 * 256)
                if not chunk:
                    break
                f.write(chunk)
                done += len(chunk)
                if total:
                    pct = done / total * 100
                    q.put(("progress", pct,
                           f"ffmpeg wird eingerichtet (einmalig) ... {pct:4.0f} %  "
                           f"({done // 1048576} / {total // 1048576} MB)"))
        with zipfile.ZipFile(zip_path) as z:
            for member in z.namelist():
                name = os.path.basename(member)
                if name in ("ffmpeg.exe", "ffprobe.exe"):
                    with z.open(member) as src, open(os.path.join(FFMPEG_DIR, name), "wb") as dst:
                        shutil.copyfileobj(src, dst)
        q.put(("ffmpeg_ready", FFMPEG_DIR))
    except Exception as e:
        q.put(("ffmpeg_failed", str(e)))
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass


# --------------------------------------------------------------------------
# Download-Logik
# --------------------------------------------------------------------------
class QuietLogger:
    def __init__(self, q):
        self.q = q

    def debug(self, msg):
        pass

    def info(self, msg):
        pass

    def warning(self, msg):
        pass

    def error(self, msg):
        self.q.put(("log", f"Fehler: {msg}"))


VIDEO_QUALITIES = {
    "Beste verfügbare": None,
    "2160p (4K)": 2160,
    "1440p (2K)": 1440,
    "1080p (Full HD)": 1080,
    "720p (HD)": 720,
    "480p": 480,
    "360p": 360,
    "240p": 240,
}
VIDEO_FORMATS = ["MP4", "MKV", "WEBM"]

AUDIO_QUALITIES = {
    "Beste verfügbare": "0",
    "320 kbit/s": "320",
    "256 kbit/s": "256",
    "192 kbit/s": "192",
    "128 kbit/s": "128",
}
AUDIO_FORMATS = ["MP3", "M4A", "WAV", "OPUS"]

SETTINGS_FILE = os.path.join(APP_DIR, "einstellungen.json")


def load_settings():
    try:
        with open(SETTINGS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_settings(data):
    try:
        os.makedirs(APP_DIR, exist_ok=True)
        with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def build_options(folder, mode, quality, fmt, playlist, ffmpeg_dir, q):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = (done / total * 100) if total else 0
            speed = (d.get("_speed_str") or "").strip()
            eta = (d.get("_eta_str") or "").strip()
            q.put(("progress", pct, f"{pct:5.1f} %   {speed}   Rest: {eta}"))
        elif d["status"] == "finished":
            q.put(("progress", 100, "Wird verarbeitet ..."))

    opts = {
        "outtmpl": os.path.join(folder, "%(title).150s [%(id)s].%(ext)s"),
        "noplaylist": not playlist,
        "progress_hooks": [hook],
        "logger": QuietLogger(q),
        "quiet": True,
        "no_warnings": True,
        "noprogress": True,
        "windowsfilenames": True,
    }
    if ffmpeg_dir:
        opts["ffmpeg_location"] = ffmpeg_dir

    if mode == "audio":
        codec = fmt.lower()
        if ffmpeg_dir:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": codec,
                "preferredquality": AUDIO_QUALITIES.get(quality, "0"),
            }]
        else:
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        container = fmt.lower()
        height = VIDEO_QUALITIES.get(quality)
        limit = f"[height<={height}]" if height else ""
        if ffmpeg_dir:
            # Höchste Auflösung bis zum gewählten Limit, bevorzugt im gewählten Format
            opts["format"] = f"bv*{limit}+ba/b{limit}/bv*+ba/b"
            if container == "webm":
                # WEBM kann nur VP9/AV1 + Opus enthalten
                opts["format"] = f"bv*{limit}[ext=webm]+ba[ext=webm]/" + opts["format"]
            sort = [f"res:{height}"] if height else ["res"]
            if container == "mp4":
                sort.append("ext:mp4:m4a")
            elif container == "webm":
                sort.append("ext:webm:webm")
            opts["format_sort"] = sort
            opts["merge_output_format"] = container
            # Falls nur ein Format ohne Zusammenfügen kommt, trotzdem ins Zielformat bringen
            if container in ("mp4", "mkv"):
                opts["postprocessors"] = [{"key": "FFmpegVideoRemuxer",
                                           "preferedformat": container}]
        else:
            # Ohne ffmpeg nur Formate mit Bild+Ton in einer Datei
            opts["format"] = f"b{limit}[ext=mp4]/b{limit}/b"

    return opts


def download_worker(urls, folder, mode, quality, fmt, playlist, ffmpeg_dir, q):
    os.makedirs(folder, exist_ok=True)
    ok = 0
    for i, url in enumerate(urls, 1):
        q.put(("log", f"[{i}/{len(urls)}] Lade: {url}"))
        try:
            opts = build_options(folder, mode, quality, fmt, playlist, ffmpeg_dir, q)
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)
                title = info.get("title", "Video") if info else "Video"
            q.put(("log", f"   ✔ Fertig: {title}"))
            ok += 1
        except Exception as e:
            q.put(("log", f"   ✘ Fehlgeschlagen: {e}"))
    q.put(("done", ok, len(urls)))


# --------------------------------------------------------------------------
# Oberfläche
# --------------------------------------------------------------------------
class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"Video-Downloader  v{VERSION}" if VERSION != "dev" else "Video-Downloader")
        self.geometry("800x740")
        self.minsize(660, 640)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.q = queue.Queue()
        self.busy = False
        self.pending_update = None
        self.ffmpeg_dir = find_ffmpeg()

        pad = {"padx": 10, "pady": 5}

        ttk.Label(self, text="Link(s) einfügen – ein Link pro Zeile:",
                  font=("Segoe UI", 10, "bold")).pack(anchor="w", **pad)

        self.links = tk.Text(self, height=6, wrap="none", font=("Consolas", 10))
        self.links.pack(fill="x", padx=10)

        btn_row = ttk.Frame(self)
        btn_row.pack(fill="x", **pad)
        ttk.Button(btn_row, text="Aus Zwischenablage einfügen",
                   command=self.paste).pack(side="left")
        ttk.Button(btn_row, text="Leeren",
                   command=lambda: self.links.delete("1.0", "end")).pack(side="left", padx=5)

        # Optionen
        opt = ttk.LabelFrame(self, text="Optionen")
        opt.pack(fill="x", **pad)

        s = load_settings()
        self.saved = s

        ttk.Label(opt, text="Typ:").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        type_row = ttk.Frame(opt)
        type_row.grid(row=0, column=1, columnspan=4, sticky="w")
        self.mode = tk.StringVar(value=s.get("mode", "video"))
        ttk.Radiobutton(type_row, text="Video", variable=self.mode, value="video",
                        command=self.on_mode_change).pack(side="left", padx=(8, 16))
        ttk.Radiobutton(type_row, text="Nur Audio", variable=self.mode, value="audio",
                        command=self.on_mode_change).pack(side="left", padx=(0, 16))
        self.playlist = tk.BooleanVar(value=False)
        ttk.Checkbutton(type_row, text="Ganze Playlist laden",
                        variable=self.playlist).pack(side="left")

        self.quality_label = ttk.Label(opt)
        self.quality_label.grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.quality = tk.StringVar()
        self.quality_box = ttk.Combobox(opt, textvariable=self.quality, state="readonly", width=20)
        self.quality_box.grid(row=1, column=1, sticky="w", padx=8)

        fmt_row = ttk.Frame(opt)
        fmt_row.grid(row=1, column=2, columnspan=3, sticky="w")
        ttk.Label(fmt_row, text="Format:").pack(side="left", padx=(8, 8))
        self.fmt = tk.StringVar()
        self.fmt_box = ttk.Combobox(fmt_row, textvariable=self.fmt, state="readonly", width=8)
        self.fmt_box.pack(side="left")

        ttk.Label(opt, text="Speicherort:").grid(row=2, column=0, sticky="w", padx=8, pady=4)
        self.folder = tk.StringVar(value=s.get("folder", DEFAULT_DIR))
        ttk.Entry(opt, textvariable=self.folder).grid(row=2, column=1, columnspan=2,
                                                      sticky="ew", padx=8)
        ttk.Button(opt, text="…", width=3, command=self.choose_folder).grid(row=2, column=3, padx=4)
        ttk.Button(opt, text="Ordner öffnen", command=self.open_folder).grid(row=2, column=4, padx=8)
        opt.columnconfigure(2, weight=1)
        self.on_mode_change(initial=True)

        # Download + Fortschritt
        self.dl_btn = ttk.Button(self, text="⬇  Download starten", command=self.start,
                                 style="Accent.TButton" if sv_ttk else "TButton")
        self.dl_btn.pack(fill="x", padx=10, pady=(8, 4), ipady=6)

        self.bar = ttk.Progressbar(self, maximum=100)
        self.bar.pack(fill="x", padx=10)
        self.status = ttk.Label(self, text="Bereit.")
        self.status.pack(anchor="w", padx=10)

        # Log
        self.log = tk.Text(self, height=10, state="disabled", font=("Consolas", 9),
                           bg="#1e1e1e", fg="#d4d4d4")
        self.log.pack(fill="both", expand=True, **pad)

        bottom = ttk.Frame(self)
        bottom.pack(fill="x", padx=10, pady=(0, 8))
        self.update_btn = ttk.Button(bottom,
                                     text="Nach Updates suchen" if FROZEN else "yt-dlp aktualisieren",
                                     command=self.update_app)
        self.update_btn.pack(side="left")
        ttk.Label(bottom, text="Design:").pack(side="left", padx=(16, 6))
        self.theme_choice = tk.StringVar(value=self.saved.get("theme", "System"))
        if self.theme_choice.get() not in THEMES:
            self.theme_choice.set("System")
        theme_box = ttk.Combobox(bottom, textvariable=self.theme_choice, state="readonly",
                                 values=list(THEMES), width=8)
        theme_box.pack(side="left")
        theme_box.bind("<<ComboboxSelected>>", self.on_theme_change)
        self.info_label = ttk.Label(bottom)
        self.info_label.pack(side="right")
        self.refresh_ffmpeg_ui()
        self.applied_theme = None
        self.apply_theme()
        self.after(2000, self.watch_system_theme)

        if not self.ffmpeg_dir:
            if sys.platform == "win32":
                self.setup_ffmpeg()
            else:
                self.write_log("Hinweis: ffmpeg nicht gefunden – bitte über den "
                               "Paketmanager installieren für beste Qualität.")

        if FROZEN:
            cleanup_old_exe()
            # Beim Start still im Hintergrund nach einem Update schauen
            self.after(1500, lambda: threading.Thread(
                target=check_for_update, args=(self.q, False), daemon=True).start())

        self.after(100, self.poll)

    # ---------- Hell / Dunkel ----------
    def effective_theme(self):
        choice = THEMES.get(self.theme_choice.get(), "system")
        if choice == "system":
            return "dark" if windows_uses_dark() else "light"
        return choice

    def apply_theme(self):
        theme = self.effective_theme()
        if theme == self.applied_theme:
            return
        self.applied_theme = theme
        if sv_ttk:
            sv_ttk.set_theme(theme)
        c = TEXT_COLORS[theme]
        self.configure(bg=ttk.Style().lookup("TFrame", "background") or c["bg"])
        self.links.config(bg=c["bg"], fg=c["fg"], insertbackground=c["fg"],
                          selectbackground=c["sel"], relief="flat", highlightthickness=1,
                          highlightbackground="#5a5a5a" if theme == "dark" else "#c8c8c8",
                          highlightcolor="#4cc2ff" if theme == "dark" else "#005fb8")
        self.log.config(bg=c["log_bg"], fg=c["log_fg"], selectbackground=c["sel"],
                        relief="flat", highlightthickness=0)
        set_titlebar_dark(self, theme == "dark")
        # Titelleiste neu zeichnen lassen
        w, h = self.winfo_width(), self.winfo_height()
        if w > 1 and h > 1:
            self.geometry(f"{w + 1}x{h}")
            self.after(10, lambda: self.geometry(f"{w}x{h}"))

    def on_theme_change(self, _event=None):
        self.saved["theme"] = self.theme_choice.get()
        save_settings(self.saved)
        self.apply_theme()

    def watch_system_theme(self):
        """Im Modus "System" Änderungen der Windows-Einstellung live übernehmen."""
        if self.theme_choice.get() == "System":
            self.apply_theme()
        self.after(2000, self.watch_system_theme)

    # ---------- Qualität / Format ----------
    def remember_choice(self):
        """Merkt sich die aktuelle Auswahl für den jeweiligen Typ."""
        if self.quality.get():
            self.saved[f"{self.current_mode}_quality"] = self.quality.get()
        if self.fmt.get():
            self.saved[f"{self.current_mode}_fmt"] = self.fmt.get()

    def on_mode_change(self, initial=False):
        if not initial:
            self.remember_choice()
        mode = self.mode.get()
        self.current_mode = mode
        if mode == "audio":
            self.quality_label.config(text="Audioqualität:")
            qualities = list(AUDIO_QUALITIES)
            formats = AUDIO_FORMATS if self.ffmpeg_dir else ["M4A"]
        else:
            self.quality_label.config(text="Auflösung:")
            qualities = list(VIDEO_QUALITIES)
            formats = VIDEO_FORMATS if self.ffmpeg_dir else ["MP4"]
        self.quality_box.config(values=qualities)
        self.fmt_box.config(values=formats)
        q = self.saved.get(f"{mode}_quality")
        f = self.saved.get(f"{mode}_fmt")
        self.quality.set(q if q in qualities else qualities[0])
        self.fmt.set(f if f in formats else formats[0])

    # ---------- ffmpeg ----------
    def refresh_ffmpeg_ui(self):
        self.on_mode_change(initial=True)
        self.info_label.config(
            text=f"App {VERSION}   |   yt-dlp {yt_dlp.version.__version__}   |   ffmpeg: "
                 + ("bereit ✔" if self.ffmpeg_dir else "fehlt ✘"))

    def setup_ffmpeg(self):
        self.busy = True
        self.dl_btn.config(state="disabled")
        self.write_log("Erster Start: ffmpeg wird einmalig eingerichtet (ca. 100 MB). "
                       "Das wird für beste Qualität und MP3 gebraucht.")
        threading.Thread(target=install_ffmpeg, args=(self.q,), daemon=True).start()

    # ---------- Aktionen ----------
    def paste(self):
        try:
            text = self.clipboard_get().strip()
        except tk.TclError:
            return
        current = self.links.get("1.0", "end").strip()
        self.links.insert("end", ("\n" if current else "") + text)

    def choose_folder(self):
        d = filedialog.askdirectory(initialdir=self.folder.get())
        if d:
            self.folder.set(d)

    def open_folder(self):
        path = self.folder.get()
        os.makedirs(path, exist_ok=True)
        if sys.platform == "win32":
            os.startfile(path)
        elif sys.platform == "darwin":
            subprocess.Popen(["open", path])
        else:
            subprocess.Popen(["xdg-open", path])

    def start(self):
        if self.busy:
            return
        urls = [u.strip() for u in self.links.get("1.0", "end").splitlines()
                if u.strip().startswith("http")]
        if not urls:
            messagebox.showwarning("Kein Link", "Bitte mindestens einen gültigen Link einfügen.")
            return
        self.remember_choice()
        self.saved["mode"] = self.mode.get()
        self.saved["folder"] = self.folder.get()
        save_settings(self.saved)

        self.busy = True
        self.dl_btn.config(state="disabled")
        self.bar["value"] = 0
        self.write_log(f"Einstellung: {'Audio' if self.mode.get() == 'audio' else 'Video'}, "
                       f"{self.quality.get()}, {self.fmt.get()}")
        threading.Thread(
            target=download_worker,
            args=(urls, self.folder.get(), self.mode.get(), self.quality.get(),
                  self.fmt.get(), self.playlist.get(), self.ffmpeg_dir, self.q),
            daemon=True,
        ).start()

    def update_app(self):
        if FROZEN:
            if self.pending_update:
                self.ask_install_update(self.pending_update)
                return
            self.update_btn.config(state="disabled")
            self.write_log("Suche nach Updates ...")
            threading.Thread(target=check_for_update, args=(self.q, True), daemon=True).start()
            return
        self.write_log("yt-dlp wird aktualisiert ...")

        def run():
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                               capture_output=True, text=True)
            msg = ("Update fertig – bitte Programm neu starten."
                   if r.returncode == 0 else f"Update fehlgeschlagen:\n{r.stderr[-500:]}")
            self.q.put(("log", msg))

        threading.Thread(target=run, daemon=True).start()

    def ask_install_update(self, info):
        if self.busy:
            messagebox.showinfo("Update", "Bitte warte, bis der aktuelle Download fertig ist.")
            return
        mb = info["size"] // 1048576 if info.get("size") else "?"
        if not messagebox.askyesno(
                "Update verfügbar",
                f"Version {info['version']} ist verfügbar (du hast {VERSION}).\n\n"
                f"Jetzt herunterladen und installieren? ({mb} MB)\n"
                "Die App startet danach automatisch neu."):
            return
        self.busy = True
        self.dl_btn.config(state="disabled")
        self.update_btn.config(state="disabled")
        self.bar["value"] = 0
        self.write_log(f"Lade Version {info['version']} herunter ...")
        threading.Thread(target=download_and_install_update, args=(info, self.q),
                         daemon=True).start()

    # ---------- GUI-Updates ----------
    def write_log(self, text):
        self.log.config(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.config(state="disabled")

    def unlock(self, status):
        self.busy = False
        self.dl_btn.config(state="normal")
        self.status.config(text=status)

    def poll(self):
        try:
            while True:
                item = self.q.get_nowait()
                kind = item[0]
                if kind == "log":
                    self.write_log(item[1])
                elif kind == "progress":
                    self.bar["value"] = item[1]
                    self.status.config(text=item[2])
                elif kind == "done":
                    ok, total = item[1], item[2]
                    self.unlock(f"Fertig: {ok} von {total} erfolgreich.")
                    self.write_log(f"=== {ok}/{total} Downloads erfolgreich ===\n")
                elif kind == "ffmpeg_ready":
                    self.ffmpeg_dir = item[1]
                    self.refresh_ffmpeg_ui()
                    self.bar["value"] = 0
                    self.unlock("Bereit.")
                    self.write_log("✔ ffmpeg ist eingerichtet. Du kannst loslegen!\n")
                elif kind == "update_available":
                    info, manual = item[1], item[2]
                    self.pending_update = info
                    self.update_btn.config(state="normal",
                                           text=f"⬆  Update auf v{info['version']} installieren")
                    self.write_log(f"Neue Version {info['version']} verfügbar.")
                    if manual:
                        self.ask_install_update(info)
                elif kind == "update_none":
                    self.update_btn.config(state="normal")
                    if item[2]:
                        self.write_log(f"Du hast bereits die neueste Version ({VERSION}).")
                        messagebox.showinfo("Kein Update", f"Du hast bereits die neueste "
                                                           f"Version ({VERSION}).")
                elif kind == "update_check_failed":
                    self.update_btn.config(state="normal")
                    if item[2]:
                        self.write_log(f"Update-Suche fehlgeschlagen: {item[1]}")
                        messagebox.showwarning("Update", "Konnte nicht nach Updates suchen. "
                                                         "Bist du mit dem Internet verbunden?")
                elif kind == "update_installed":
                    self.write_log(f"✔ Version {item[1]} installiert – App startet neu ...")
                    self.after(800, self.destroy)
                elif kind == "update_failed":
                    self.bar["value"] = 0
                    self.update_btn.config(state="normal")
                    self.unlock("Bereit.")
                    self.write_log(f"✘ Update fehlgeschlagen: {item[1]}")
                    if messagebox.askyesno("Update fehlgeschlagen",
                                           f"Das Update hat nicht geklappt:\n{item[1]}\n\n"
                                           "Download-Seite im Browser öffnen?"):
                        webbrowser.open(RELEASES_URL)
                elif kind == "ffmpeg_failed":
                    self.bar["value"] = 0
                    self.unlock("Bereit (ohne ffmpeg).")
                    self.write_log(f"✘ ffmpeg konnte nicht eingerichtet werden: {item[1]}\n"
                                   "Downloads funktionieren trotzdem, teils in geringerer "
                                   "Qualität. Beim nächsten Start wird es erneut versucht.\n")
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    App().mainloop()
