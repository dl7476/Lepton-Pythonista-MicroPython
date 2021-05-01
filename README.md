# Lepton-Pythonista-MicroPython
This project aims at streaming the thermal video of a FLIR Lepton on a Iphone. The video stream is retrieved by an ESP32 through the VoSPI of the Lepton and then the EPS32 sends
to the Iphone through Wifi /UDP the video. A first program is written in Micropython for the ESP32. This one sets up the Lepton configuration through the CCI and gets the video data
from the Lepton and sends it to the Iphone without any processing. A second program is written in Pythonista for the Iphone. This one processes the data received and displays the 
images/video. The program enables the user to choose the mode : 1) AGC (8 bit grayscale) 2) RAD /T Linear , RGB. In the second mode the user can get the temperrature through touching
the screen. CAUTION : the program does not involve any calibration of the Lepton. The user can zoom and takes some screenshots (two buttons at the bottom of the screen for 
this purpose)

Hardware
Iphone (8)
ESP32 Wroom (from uPesy)
jumper cables + breadboard
Lepton 3.5
Breakout board V2.0

 
