# Video-Downloader

Einfaches Programm mit Fenster, um Videos von YouTube, TikTok, Instagram, X, Twitch, Reddit und über 1000 weiteren Seiten herunterzuladen – Link einfügen, auf „Download“ klicken, fertig.

Basiert auf [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Funktionen

- Mehrere Links auf einmal (ein Link pro Zeile)
- Video als MP4 in bester Qualität oder nur Audio als MP3
- Ganze Playlists auf Wunsch
- Fortschrittsanzeige mit Geschwindigkeit und Restzeit
- Speicherort frei wählbar (Standard: `Downloads\Video-Downloader`)
- Button zum Aktualisieren von yt-dlp, falls eine Seite plötzlich nicht mehr klappt

## Installation (Windows)

1. **Python installieren**: https://www.python.org/downloads/
   Beim Installieren unbedingt den Haken bei **„Add python.exe to PATH“** setzen.
2. **ffmpeg installieren** (empfohlen, für beste Qualität und MP3):
   Eingabeaufforderung öffnen und eingeben:
   ```
   winget install Gyan.FFmpeg
   ```
3. Dieses Repository herunterladen: oben auf **Code → Download ZIP**, dann entpacken.
4. **`Start.bat`** doppelklicken. Beim ersten Start wird yt-dlp automatisch installiert.

## Benutzung

1. Link(s) in das obere Feld einfügen (oder „Aus Zwischenablage einfügen“ klicken)
2. Video oder Audio auswählen
3. **Download starten** klicken
4. Mit **Ordner öffnen** gelangst du direkt zu den Dateien

Wenn eine Seite nicht mehr funktioniert: **yt-dlp aktualisieren** klicken und das Programm neu starten.

## Hinweis

Lade nur Inhalte herunter, die du herunterladen darfst – z. B. eigene Videos, freie Inhalte oder solche, für die du die Erlaubnis hast. Die Nutzungsbedingungen mancher Plattformen verbieten das Herunterladen.
