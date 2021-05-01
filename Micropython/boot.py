import network
import machine
import utime

machine.freq(240000000)



import esp
esp.osdebug(None)

import gc
gc.collect()


#access point, ssid & password to be defined by the user
ssid = 'XXXX'
password = 'XXXX'



#access point
station = network.WLAN(network.AP_IF)

station.active(True)

station.config(essid=ssid,password=password)

while station.active() == False:
    pass

print('Connection successful')
print(station.ifconfig())



