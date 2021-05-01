# Lepton-Pythonista-MicroPython
This project aims at streaming the thermal video of a FLIR Lepton on a Iphone. The video stream is retrieved by an ESP32 through the VoSPI of the Lepton and then the EPS32 sends
to the Iphone through Wifi /UDP the video. A first program is written in Micropython for the ESP32. This one sets up the Lepton configuration through the CCI and gets the video data
from the Lepton and sends it to the Iphone without any processing. A second program is written in Pythonista for the Iphone. This one processes the data received and displays the 
images/video. The program enables the user to choose the mode : 1) AGC (8 bit grayscale) 2) RAD /T Linear , RGB. In the second mode the user can get the temperrature through touching
the screen. CAUTION : the program does not involve any calibration of the Lepton. The user can zoom and takes some screenshots (two buttons at the bottom of the screen for 
this purpose)

## **Hardware**
- Iphone (8)
- ESP32 Wroom DevKit (from uPesy)
- jumper cables + breadboard
- Lepton 3.5
- Breakout board V2.0

## **Preparation**
1) in boot.py set up the password and ssid 
2) in main.py : set up the TIMEOUT, the streaming lasts the duration specified by TIMEOUT. If you want that the loop runs forever, replace the duration in the "while loop" by "true" 
3) cabling according to the Lepton Breakout board V2.0 electrical scheme and https://lepton.flir.com/getting-started/raspberry-pi-lepton/ + MOSI grounded

## **Usage**
- power up the ESP32, after 5 s, the blue LED blinks at 1 Hz, it means that the ESP32 waits for the mode selection coming from the Pythonista program
- in the Iphone , go to the wifi configuration panel and choose the relevant Wifi access point (that you have specified at 1) in "preparation" above). Check that the Wifi logo 
  has appeared on the Iphone screen  
- run the Pythonista program , select the mode, the blue LED of the ESP32 blinks then faster (10 Hz) until the intilisation is complete
- when the initialisation is complete, the LED remains fixed, the video appears on the Iphone two seconds after 
- the user can zoom (1 , 1.5, 2, 2.5, 3, whole width), takes a screenshot (files are named screenshot0X.jpg, the previous files are erased) 
- in RAD mode (RGB), the user can get the temperature through touching the view 
- Top screen : Bad CRC : information about the communication quality, usually around 20-25%. qsize :queue shared between the thread that receipts the data and the one that       processes the data, if everything is fine, qsize should be not more than 2 (=processing faster than data receiption). fps : frame per second, should be 9 (at least outside US, perhaps in US can be 27?). T (only in RAD mode) : temperature got after having touched the view (a white dot appears when the screen is touched, see video example) 
- RGB : the palette used can be found in "Pythonista" folder, the program adapts the color to the the current scene temperature range 
- Streaming duration : see remark at 2) above in "preparation"
- during the video streaming, the user can stop the Pythonista program and run it again but the user has to choose the same mode as initially specified (it is not possible to change the mode during the streaming). If the user wants to switch to a different mode, the ESP32 must be reset (then the blue LED blinks at 1 Hz, etc...) 


