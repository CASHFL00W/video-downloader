"""
Video-Downloader – YouTube, TikTok, Instagram, X, Twitch, Reddit u.v.m.
Einfach Link(s) einfügen und auf "Download" klicken.

Basiert auf yt-dlp (https://github.com/yt-dlp/yt-dlp).
"""

import os
import sys
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


def build_options(folder, mode, playlist, ffmpeg_dir, q):
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
        if ffmpeg_dir:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        if ffmpeg_dir:
            # Beste Qualität, Bild + Ton zu MP4 zusammengefügt
            opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
            opts["merge_output_format"] = "mp4"
        else:
            # Ohne ffmpeg nur Formate mit Bild+Ton in einer Datei
            opts["format"] = "b[ext=mp4]/b"

    return opts


def download_worker(urls, folder, mode, playlist, ffmpeg_dir, q):
    os.makedirs(folder, exist_ok=True)
    ok = 0
    for i, url in enumerate(urls, 1):
        q.put(("log", f"[{i}/{len(urls)}] Lade: {url}"))
        try:
            with yt_dlp.YoutubeDL(build_options(folder, mode, playlist, ffmpeg_dir, q)) as ydl:
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
        self.title("Video-Downloader")
        self.geometry("720x580")
        self.minsize(560, 480)
        try:
            self.iconbitmap(resource_path("icon.ico"))
        except Exception:
            pass

        self.q = queue.Queue()
        self.busy = False
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

        self.mode = tk.StringVar(value="video")
        ttk.Radiobutton(opt, text="Video (MP4)", variable=self.mode,
                        value="video").grid(row=0, column=0, sticky="w", padx=8, pady=4)
        self.audio_rb = ttk.Radiobutton(opt, variable=self.mode, value="audio")
        self.audio_rb.grid(row=0, column=1, sticky="w", padx=8)
        self.playlist = tk.BooleanVar(value=False)
        ttk.Checkbutton(opt, text="Ganze Playlist laden",
                        variable=self.playlist).grid(row=0, column=2, sticky="w", padx=8)

        ttk.Label(opt, text="Speicherort:").grid(row=1, column=0, sticky="w", padx=8, pady=4)
        self.folder = tk.StringVar(value=DEFAULT_DIR)
        ttk.Entry(opt, textvariable=self.folder).grid(row=1, column=1, columnspan=2,
                                                      sticky="ew", padx=8)
        ttk.Button(opt, text="…", width=3, command=self.choose_folder).grid(row=1, column=3, padx=4)
        ttk.Button(opt, text="Ordner öffnen", command=self.open_folder).grid(row=1, column=4, padx=8)
        opt.columnconfigure(2, weight=1)

        # Download + Fortschritt
        self.dl_btn = ttk.Button(self, text="⬇  Download starten", command=self.start)
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
        ttk.Button(bottom, text="Nach Updates suchen" if FROZEN else "yt-dlp aktualisieren",
                   command=self.update_app).pack(side="left")
        self.info_label = ttk.Label(bottom)
        self.info_label.pack(side="right")
        self.refresh_ffmpeg_ui()

        if not self.ffmpeg_dir:
            if sys.platform == "win32":
                self.setup_ffmpeg()
            else:
                self.write_log("Hinweis: ffmpeg nicht gefunden – bitte über den "
                               "Paketmanager installieren für beste Qualität.")

        self.after(100, self.poll)

    # ---------- ffmpeg ----------
    def refresh_ffmpeg_ui(self):
        self.audio_rb.config(text="Nur Audio (MP3)" if self.ffmpeg_dir else "Nur Audio (M4A)")
        self.info_label.config(
            text=f"yt-dlp {yt_dlp.version.__version__}   |   ffmpeg: "
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
        self.busy = True
        self.dl_btn.config(state="disabled")
        self.bar["value"] = 0
        threading.Thread(
            target=download_worker,
            args=(urls, self.folder.get(), self.mode.get(), self.playlist.get(),
                  self.ffmpeg_dir, self.q),
            daemon=True,
        ).start()

    def update_app(self):
        if FROZEN:
            self.write_log("Öffne Download-Seite der neuesten Version ...")
            webbrowser.open(RELEASES_URL)
            return
        self.write_log("yt-dlp wird aktualisiert ...")

        def run():
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"],
                               capture_output=True, text=True)
            msg = ("Update fertig – bitte Programm neu starten."
                   if r.returncode == 0 else f"Update fehlgeschlagen:\n{r.stderr[-500:]}")
            self.q.put(("log", msg))

        threading.Thread(target=run, daemon=True).start()

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
