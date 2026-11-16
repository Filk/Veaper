VEAPER
Convert a DaVinci Resolve AAF export into a Reaper project (.rpp).

Veaper reads the timeline from a Resolve AAF file, converts referenced MXF audio
to WAV, and builds a Reaper project with clip positions, source in-points,
fades, volume, pan, and playback speed where available in the AAF.

Step-by-step tutorial for exporting from DaVinci Resolve:
https://filipelopes.net/veaper

---
USE THE APP

You do not need Python, pip, or a terminal.

Mac
1. Unzip Veaper-mac.zip.
2. Move Veaper.app to your Applications folder.
3. The first time, macOS will say it cannot verify the developer.
   Right-click Veaper, choose Open, then choose Open again.
   If that choice is missing, open System Settings, go to Privacy & Security,
   and click Open Anyway.
4. Click "1. Choose AAF file".
5. Click "2. Create Reaper project" and wait. Large projects take a few minutes.
6. Open the project in Reaper:
   inside the AAF's folder, open Reaper_from_DaVinci/my_project.rpp

You can also drop an AAF file onto the Veaper icon.

Windows
1. Unzip Veaper-windows.zip.
2. Double-click Veaper.exe.
   Windows may ask you to confirm because the app is not from the Store.
3. Follow the same two steps as on Mac.

Keep every MXF file in the same folder as the AAF. The WAV files have to stay
next to my_project.rpp, or Reaper will not find them.

The Mac app built here is for Apple Silicon Macs.

---
WHAT THE APP CREATES

Inside the folder where your AAF lives:

Reaper_from_DaVinci/my_project.rpp
Reaper_from_DaVinci/*.wav
Reaper_from_DaVinci/Audio_data_from_aaf.json

---
BUILDING THE APP

This is only for someone preparing a copy of Veaper for other people.
The finished app does not need these tools.

Mac (Apple Silicon), from this folder:

/opt/homebrew/bin/python3.12 -m venv .venv
.venv/bin/python build_standalone.py

The app is written to dist/Veaper.app
A zip you can send is written to dist/Veaper-mac.zip

Windows, from this folder, in Command Prompt:

py -3.12 -m venv .venv
.venv\Scripts\python build_standalone.py

The program is written to dist\Veaper.exe

A tagged GitHub release (v*) also builds both apps.

---
RUNNING FROM SOURCE

Mac:
python3 -m pip install pyaaf2
brew install ffmpeg
python3 Veaper.py

Windows:
py -3 -m pip install pyaaf2
Install FFmpeg from https://ffmpeg.org/download.html and add it to PATH.
py Veaper.py

FFmpeg has to be available as the ffmpeg command. MoviePy is not used.

---
NOTES

- If the AAF references many MXF files, the first run may take several minutes.
- Reaper resolves media paths relative to the .rpp file, so keep the WAV files
  inside Reaper_from_DaVinci/ alongside my_project.rpp.
- FFmpeg is bundled inside the standalone app and run as a separate program.
  This copy is FFmpeg 9.0, licensed under the GNU GPL. Source and license:
  https://ffmpeg.org/download.html

---
CREDITS

Coding: Filipe Lopes
Help to test: Luís Rocha
Icon: https://www.flaticon.com/free-icon/multimedia_2205491?term=video&page=1&position=9&origin=search&related_id=2205491
