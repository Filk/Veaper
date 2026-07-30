VEAPER
Convert a DaVinci Resolve AAF export into a Reaper project (.rpp).

Veaper reads the timeline from a Resolve AAF file, converts referenced MXF audio
to WAV, and builds a Reaper project with clip positions, source in-points,
fades, volume, pan, and playback speed where available in the AAF.

Step-by-step tutorial for exporting from DaVinci Resolve:
https://filipelopes.net/veaper

---
REQUIREMENTS

- Python 3.9 or newer
- FFmpeg (required by MoviePy for MXF audio conversion)
- Your AAF file and its MXF media files in the same folder

---
INSTALLATION

1] Install Python 3

   Download from https://www.python.org/
   During installation, enable "Add Python to PATH" (Windows).

   Verify:
   Mac:     python3 --version
   Windows: python --version

2] Install FFmpeg

   MoviePy needs FFmpeg to extract audio from MXF files.

   Mac (Homebrew):  brew install ffmpeg
   Windows:         download from https://ffmpeg.org/download.html
                    and add ffmpeg to your PATH

   Verify:  ffmpeg -version

3] Install Python dependencies

   Mac:
   pip3 install pyaaf2 moviepy

   Windows:
   pip install pyaaf2 moviepy

4] Download this repository

   git clone https://github.com/Filk/Veaper.git
   or download the ZIP from GitHub.

---
HOW TO USE

1. Export an AAF from DaVinci Resolve (see tutorial link above).
2. Keep all MXF (and other linked media) files in the same folder as the AAF.
3. Open a terminal/command prompt and go to the Veaper folder.
4. Run the app:

   Mac:
   python3 Veaper.py

   Windows:
   python Veaper.py

5. In the app:
   - Click the grey area and select your .aaf file
   - Click "Click here to start process and wait"
   - Wait until processing finishes (MXF conversion can take a while)

6. Open the output in Reaper:

   Inside the folder where your AAF lives, open:
   Reaper_from_DaVinci/my_project.rpp

   That folder also contains:
   - converted .wav files
   - Audio_data_from_aaf.json (debug/reference data)

---
NOTES

- Pre-built Mac/Windows apps may not be available on the Releases page.
  Running from source (instructions above) is the recommended method for now.
- If the AAF references many MXF files, the first run may take several minutes.
- Reaper resolves media paths relative to the .rpp file, so keep the WAV files
  inside Reaper_from_DaVinci/ alongside my_project.rpp.

---
BUILDING A STANDALONE APP (OPTIONAL)

Developers can package Veaper with PyInstaller:

   pip install pyinstaller
   pyinstaller --onefile --windowed Veaper.py

---
CREDITS

Coding: Filipe Lopes
Help to test: Luís Rocha
Icon: https://www.flaticon.com/free-icon/multimedia_2205491?term=video&page=1&position=9&origin=search&related_id=2205491
