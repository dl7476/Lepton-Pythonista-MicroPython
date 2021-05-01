from machine import SoftI2C, Pin, SPI, PWM
import utime
import usocket as socket



LEPTON_ADDR=0x2A


# SPI speed : 20 MHz -> 3.9 ms to retrieve one segment (164 x 60 x 8 = 78720 bits) in RAW14 format. Measurment in "loop": 4-5 ms (4300-4400 us)
# SPI+UDP (sendto segment of 164x60 bytes): 7-8 ms . UDP speed : around 30 Mb/s (2600 us / segment), as indicated by Espressif
# VSYNC  frequency : 27x4 Hz -> every 9.25 ms.  Note : RGB888 packet size : 244 ,cannot be sent on time through UDP sendto  

PACKET_SIZE=164 

#timeout  mn and ms
TIMEOUT_MN=2
TIMEOUT=TIMEOUT_MN*60*1000

#register addresses related to the control interface (CCI)
STATUS_REG=bytearray([0x0000,0x0002])
COMMAND_REG=bytearray([0x0000,0x0004])
DATA_LENGTH_REG=bytearray([0x0000,0x0006])
DATA_REG=bytearray([0x0000,0x0008])
COMMAND_DICT={ 'GET':0x00, 'SET':0x01, 'RUN':0x02}

#VSYNC flag / IRQ
irq_flag=False

#frame handling follow-up, option / debug
tab=[]


#can be used to monitor the VSYNC frequency , see get_frame below, for debug
deboun1=None
deboun2=None
tab2=[]


    

def get_frame(pin):
    global irq_flag,tab2,deboun1,deboun2
    #if deboun1==None:
    #    deboun1=utime.ticks_ms()
    #deboun2=utime.ticks_ms()
    #tab2.append(utime.ticks_diff(deboun2,deboun1))
    irq_flag=True
    #deboun1=deboun2
    


#the following functions are used with the control interface (CCI) (check_busy -> run_seq)
def check_status_bit():
    #reads the status bit in the status register
    res=bytearray([0x0,0x0])
    i2c.writeto(LEPTON_ADDR,STATUS_REG,False)
    i2c.readfrom_into(LEPTON_ADDR,res)
    while ((res[1] >> 2) & 1)!=1:
        utime.sleep_ms(500)
        i2c.writeto(LEPTON_ADDR,STATUS_REG,False)
        i2c.readfrom_into(LEPTON_ADDR,res)

  
def check_busy():
    #reads the BUSY bit in the status register
    res=bytearray([0x0,0x1])
    while (res[1] & 1)!=0:
        i2c.writeto(LEPTON_ADDR,STATUS_REG,False)
        i2c.readfrom_into(LEPTON_ADDR,res)
    
def write_data_length(length):
    #sends the data length to the data length register
    buff=bytearray([0x0,length])
    i2c.start()
    i2c.write(bytearray([LEPTON_ADDR << 1]))
    i2c.write(DATA_LENGTH_REG)
    i2c.write(buff)
    i2c.stop()

    
def write_command(c,command_type):
    #sends the command to the commmand register
    module_ID,command_ID=c
    if module_ID==0x0800 or module_ID==0x0E00:
        protection_bit=0x4000
    else:
        protection_bit=0x0000
    command_type=COMMAND_DICT[command_type]
    com=protection_bit+module_ID+command_ID+command_type
    com_msb=com >> 8
    com_lsb=com & 0xFF
    buff=bytearray([com_msb,com_lsb])
    i2c.start()
    i2c.write(bytearray([LEPTON_ADDR << 1]))
    i2c.write(COMMAND_REG)
    i2c.write(buff)
    i2c.stop()
    
def check_error_code():
    #checks the error code in the status register
    res=bytearray([0x0,0x0])
    i2c.writeto(LEPTON_ADDR,STATUS_REG,False)
    i2c.readfrom_into(LEPTON_ADDR,res)
    return res[0]


def read_data_reg(res):
    #reads the data in the data registers 
    i2c.writeto(LEPTON_ADDR,DATA_REG,False)
    i2c.readfrom_into(LEPTON_ADDR,res)
  

def write_data_reg(buff):
    #writes the data in the data registers
    i2c.start()
    i2c.write(bytearray([LEPTON_ADDR << 1]))
    i2c.write(DATA_REG)
    i2c.write(buff)
    i2c.stop()
      

#main functions below : read, write and run . See Lepton SW IDD 
def read_data(c,res):
    check_busy()
    write_data_length(len(res) // 2)
    write_command(c,'GET')
    check_busy()
    err=check_error_code()
    if err==0:
        read_data_reg(res)
    return err

def write_data(c,buff):
    check_busy()
    write_data_reg(buff) 
    write_data_length(len(buff) // 2)
    write_command(c,'SET')
    check_busy()
    return check_error_code()


def run_seq(c):
    check_busy()
    write_command(c,'RUN')
    check_busy()
    return check_error_code()



def check_SYS_FFC():
    global tab
    data=bytearray([0,1,0,0])
    while data[1]!=0:
        c=read_data((0x200,0x44),data)
        tab.append(data[1])
    

#this function enables AGC (grayscale on 8 bits)  + it is necessary to disable rad
def enable_AGC():
    #enable AGC
    data2=bytearray([0,1,0,0])
    c=write_data((0x100,0x00),data2)
        
    #disable RAD
    data2=bytearray(4)
    c=write_data((0x0E00,0x10),data2)
    

def set_mode():
    s=socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(('', 7677))
    s.listen(5)
    while True:
        conn, addr = s.accept()
        print('connection from: ',str(addr))
        request = conn.recv(1024)
        request=request.decode()
        if request in ['L', 'RGB']:
            conn.sendall(b'OK')
            conn.close()
            return request
        else:
            conn.close()
        
   

#frame counter
indice=0
#buffer used to retrieve video through SPI and used by sendto (UDP) 
buff_video=bytearray(PACKET_SIZE*60)
#exception occurences
nbre_ex=0
#exception follow up to avoid ENOMEM bug 
#https://github.com/espressif/esp-idf/issues/390
flag_ex=False
t1_ex=None


#5 s to be ensured between the first communication with the CCI & the power-up (only useful after a power up)
utime.sleep_ms(5000)

p2=Pin(2,Pin.OUT)
pw2=PWM(p2,freq=1,duty=256)

v_mode=set_mode()

pw2.freq(10)
pw2.duty(512)


#socket used to send segments 
s=socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

#Pin related to VSYNC
p4=Pin(16,Pin.IN)

#I2C for CCI
i2c=SoftI2C(sda=Pin(21),scl=Pin(22))

#initialisation : 1) reboot to ensure an operational state & to get the default parameters (in particular if the ESP32 is reset through EN) 2) enables AGC & disables RAD 3) GPIO Mode VSYNC    -> grayscale on 8 bits 
check_status_bit()
check_busy()
write_command((0x800,0x40),'RUN')
utime.sleep_ms(5200)

check_status_bit()
check_busy()
check_SYS_FFC()

# AGC
if v_mode=='L':
    enable_AGC()

#VSYNC
data=bytearray([0,5,0,0])
c=write_data((0x800,0x54),data)

#IRQ activation
p4.irq(handler=get_frame,trigger=Pin.IRQ_RISING)

#SPI at 20 MHz , the max according to the Lepton documentation
vspi=SPI(2,baudrate=20000000,polarity=1,phase=1,sck=Pin(18),mosi=Pin(23), miso=Pin(19))
cs=Pin(5,Pin.OUT)
cs.value(1)
utime.sleep_ms(186)


if c==0:
     
    pw2.deinit()
    p2.value(1)

    deadline = utime.ticks_add(utime.ticks_ms(), TIMEOUT)
    #/CS asserted
    cs.value(0)
    
    while (utime.ticks_diff(deadline, utime.ticks_ms()) > 0):
        if irq_flag:
            #p1=utime.ticks_us()
            
            #get the segments through SPI
            vspi.readinto(buff_video)
            #delta_t=utime.ticks_diff(utime.ticks_us(),p1)
            # exception , ENOMEM bug 
            if flag_ex:
                if utime.ticks_diff(utime.ticks_ms(),t1_ex)>50:
                    flag_ex=False
            #do not send the first frames and do not send during 50 ms if an exception has been raised
            if indice>=27*4*2 and not flag_ex:
                try:
                    #p1=utime.ticks_us()
                    s.sendto(buff_video,('192.168.4.2',7674))
                    #delta_t=utime.ticks_diff(utime.ticks_us(),p1)
                except OSError as e:
                    #ENOMEM exception , bug
                    if e.args[0]==12:
                        flag_ex=True
                        t1_ex=utime.ticks_ms()
                        nbre_ex=nbre_ex+1
                    else:
                        print('exception')
                        break
                
            indice=indice+1
            irq_flag=False
            
            #delta_t=utime.ticks_diff(utime.ticks_ms(),p1)
            #if indice<433:
            #    tab.append(delta_t)
    irq_flag=False
else:
    print('GPIO mode error')
#/CS deasserted 
cs.value(1)

#IRQ release 
p4.irq(handler=None,trigger=Pin.IRQ_RISING)

#close UDP
s.close()
s=None

#SPI release
vspi.deinit()

p2.value(0)

print('frame qty',indice,'frame handling',len(tab))
#print('irq',tab2)
print('exception qty',nbre_ex)



