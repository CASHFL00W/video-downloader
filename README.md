# Video-Downloader

Einfache Windows-App, um Videos von YouTube, TikTok, Instagram, X, Twitch, Reddit und über 1000 weiteren Seiten herunterzuladen – Link einfügen, auf „Download“ klicken, fertig.

## ⬇ Download

**[VideoDownloader.exe herunterladen](https://github.com/CASHFL00W/video-downloader/releases/latest/download/VideoDownloader.exe)**

Einfach doppelklicken – keine Installation, kein Python nötig.

> Windows zeigt beim ersten Start evtl. „Der Computer wurde durch Windows geschützt“, weil die App nicht von einer großen Firma signiert ist. Dann auf **Weitere Informationen → Trotzdem ausführen** klicken.

Beim allerersten Start richtet die App einmalig ffmpeg ein (ca. 100 MB, dauert je nach Internet ein paar Sekunden bis Minuten). Das wird für beste Qualität und MP3 gebraucht.

## Funktionen

- Mehrere Links auf einmal (ein Link pro Zeile)
- Auflösung wählbar: Beste, 4K, 2K, 1080p, 720p, 480p, 360p, 240p
- Videoformat: MP4, MKV oder WEBM
- Nur Audio: MP3, M4A, WAV oder OPUS in wählbarer Qualität (bis 320 kbit/s)
- Merkt sich deine letzten Einstellungen
- Aktualisiert sich selbst per Knopfdruck
- Modernes Windows-11-Design in Hell, Dunkel oder automatisch wie Windows (System)
- Ganze Playlists auf Wunsch
- Fortschrittsanzeige mit Geschwindigkeit und Restzeit
- Speicherort frei wählbar (Standard: `Downloads\Video-Downloader`)

## Eine Seite funktioniert plötzlich nicht mehr?

YouTube, TikTok & Co. ändern öfter etwas. Die App prüft beim Start automatisch, ob es eine neue Version gibt. Mit einem Klick auf **Update installieren** wird sie heruntergeladen, eingespielt und die App startet neu – ohne Umweg über GitHub.

## Hinweis

Lade nur Inhalte herunter, die du herunterladen darfst – z. B. eigene Videos, freie Inhalte oder solche, für die du die Erlaubnis hast. Die Nutzungsbedingungen mancher Plattformen verbieten das Herunterladen.

---

<details>
<summary>Für Entwickler</summary>

Aus dem Quellcode starten: `python video_downloader.py` (Python 3.10+, yt-dlp wird beim ersten Start automatisch installiert).

Bei jedem Push auf `main` baut GitHub Actions automatisch eine neue `VideoDownloader.exe` und veröffentlicht sie als Release.

Basiert auf [yt-dlp](https://github.com/yt-dlp/yt-dlp).
</details>
