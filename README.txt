VEAPER
Convert an Avid AAF Resolve Da Vinci Project to a Reaper Project
Check the Releases page on this repository to download the app for Mac or Windows.

---
for a step-by-step tutorial on what to do in Resolve Da Vinci:
https://filipelopes.net/veaper
--

If you want to hack the code or use it from the command line, please do the following:

1]
Install Python 3
1 - Visit the official Python website: https://www.python.org/
2 - Go to the Downloads section and download the latest version.
3 - Choose either the 32-bit or 64-bit version, depending on your system
4 - On the first page of the installer, make sure to check the box that says "Add Python 3.x to PATH". This will allow you to use Python from the command line (WINDOWS) or Terminal (MAC) easily.
5 - If you are running Windows, don´t forget to restart (of course...windows... ;))
6 -  To verify the installation, you can open the command prompt and type python3 --version (MAC) or python --version (WINDOWS). You should see the version number of Python displayed.

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

You should see now the app ready to be used.

5]
I have used pyinstaller library to compile and create the apps.

--
KNOWN BUGS (last updated on 3 june 2025):
Windows:
	a) when running the app, sometimes i get the message - "NoneType" object has no attributte ´write´ -. I haven´t find time to fix this. According to stackoverflow: " NoneType means that instead of an instance of whatever Class or Object you think you're working with, you've actually got None. That usually means that an assignment or function call up above failed or returned an unexpected result.". If I run the code through the terminal, it runs fine.

Mac:
	a) when I open the app, it will tell me it is from an unknown identifier, thus, it will not open. You have to give it permission to open in Preferences -> Security & Privacy.
	b) when I open the app, after permission were given, sometimes it does not open right away. I have to click two or three times, but it will open.
	c) when it is converting the Da Vinci to Reaper, sometimes it opens a new window with the same app. Ignore that and close it. It is a known bug combining Mac + Python and PyInstaller.
	
--
CREDITS:
Coding: Filipe Lopes
Help to test: Luís Rocha
Icon: https://www.flaticon.com/free-icon/multimedia_2205491?term=video&page=1&position=9&origin=search&related_id=2205491
