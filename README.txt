VEAPER
Convert an Avid AAF Resolve Da Vinci Project to a Reaper Project

Check the Releases page on this repository to download the app for Mac or Windows.

---
for a step-by-step tutorial on what to do in Resolve Da Vinci:
https://filipelopes.net/veaper

Icon from:
https://www.flaticon.com/free-icon/multimedia_2205491?term=video&page=1&position=9&origin=search&related_id=2205491

--

If you want to hack the code, please do the following:

1]
Install Python 3
1 - Visit the official Python website: https://www.python.org/
2 - Go to the Downloads section and download the latest version.
3 - Choose either the 32-bit or 64-bit version, depending on your system
4 - On the first page of the installer, make sure to check the box that says "Add Python 3.x to PATH". This will allow you to use Python from the command line (WINDOWS) or Terminal (MAC) easily.
5-  To verify the installation, you can open the command prompt and type python3 --version. You should see the version number of Python displayed.

2] 
Now you need to install two externals libraries. To do it, you need to open the command line (WINDOWS) or Terminal (MAC) and type:
“pip3 install pyaaf2”
	this command will install the library pyaaf2
pip3 install moviepy
	this command will install the library moviepy

*** in windows it might not be necessary to type "pip3. You can just type "pip" and keep the rest the same.

3] 
Download the source code from this repository

4]
On command line (or terminal), go to the directory where the source code is and then run:

on Mac: 
python3 Veaper.py

on Windows:
python Veaper.py
