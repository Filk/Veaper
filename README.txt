VEAPER

Convert a AAF Resolve Da Vinci to a Reaper Project.
Download the compiled apps or download the source code.

for a step-by-step tutorial on what to do in Resolve Da Vinci:
http://filipelopes.net/veaper

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

3] 
On command line (or terminal), run: 
python3 Veaper.py

in windows try:
python Veaper.py