"""
Video-Downloader – YouTube, TikTok, Instagram, X, Twitch, Reddit u.v.m.
Einfach Link(s) einfügen und auf "Download" klicken.

Basiert auf yt-dlp (https://github.com/yt-dlp/yt-dlp).
"""

import os
import sys
import queue
import shutil
import subprocess
import threading
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# --------------------------------------------------------------------------
# yt-dlp beim ersten Start automatisch installieren
# --------------------------------------------------------------------------
def ensure_ytdlp():
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        print("yt-dlp wird installiert ... (nur beim ersten Start)")
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"]
        )
    import yt_dlp
    return yt_dlp


yt_dlp = ensure_ytdlp()

HAS_FFMPEG = shutil.which("ffmpeg") is not None
DEFAULT_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "Video-Downloader")


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


def build_options(folder, mode, playlist, q):
    def hook(d):
        if d["status"] == "downloading":
            total = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            done = d.get("downloaded_bytes", 0)
            pct = (done / total * 100) if total else 0
            speed = d.get("_speed_str", "").strip()
            eta = d.get("_eta_str", "").strip()
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
        "windowsfilenames": True,
    }

    if mode == "audio":
        if HAS_FFMPEG:
            opts["format"] = "bestaudio/best"
            opts["postprocessors"] = [{
                "key": "FFmpegExtractAudio",
                "preferredcodec": "mp3",
                "preferredquality": "192",
            }]
        else:
            opts["format"] = "bestaudio[ext=m4a]/bestaudio/best"
    else:
        if HAS_FFMPEG:
            # Beste Qualität, Bild + Ton zu MP4 zusammengefügt
            opts["format"] = "bv*[ext=mp4]+ba[ext=m4a]/bv*+ba/b"
            opts["merge_output_format"] = "mp4"
        else:
            # Ohne ffmpeg nur Formate mit Bild+Ton in einer Datei
            opts["format"] = "b[ext=mp4]/b"

    return opts


def download_worker(urls, folder, mode, playlist, q):
    os.makedirs(folder, exist_ok=True)
    ok = 0
    for i, url in enumerate(urls, 1):
        q.put(("log", f"[{i}/{len(urls)}] Lade: {url}"))
        try:
            with yt_dlp.YoutubeDL(build_options(folder, mode, playlist, q)) as ydl:
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
        self.geometry("720x560")
        self.minsize(560, 460)
        self.q = queue.Queue()
        self.busy = False

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
        ttk.Radiobutton(opt, text="Nur Audio (MP3)" if HAS_FFMPEG else "Nur Audio (M4A)",
                        variable=self.mode, value="audio").grid(row=0, column=1, sticky="w", padx=8)
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
        ttk.Button(bottom, text="yt-dlp aktualisieren",
                   command=self.update_ytdlp).pack(side="left")
        ttk.Label(bottom, text=f"yt-dlp {yt_dlp.version.__version__}   |   ffmpeg: "
                  + ("gefunden ✔" if HAS_FFMPEG else "nicht gefunden ✘")).pack(side="right")

        if not HAS_FFMPEG:
            self.write_log("Hinweis: ffmpeg wurde nicht gefunden. Downloads funktionieren, "
                           "aber teils nur in geringerer Qualität und Audio nicht als MP3.\n"
                           "Installieren (Windows, Eingabeaufforderung):  winget install Gyan.FFmpeg\n"
                           "Danach das Programm neu starten.")

        self.after(100, self.poll)

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
            args=(urls, self.folder.get(), self.mode.get(), self.playlist.get(), self.q),
            daemon=True,
        ).start()

    def update_ytdlp(self):
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
                    self.busy = False
                    self.dl_btn.config(state="normal")
                    self.status.config(text=f"Fertig: {ok} von {total} erfolgreich.")
                    self.write_log(f"=== {ok}/{total} Downloads erfolgreich ===\n")
        except queue.Empty:
            pass
        self.after(100, self.poll)


if __name__ == "__main__":
    App().mainloop()
