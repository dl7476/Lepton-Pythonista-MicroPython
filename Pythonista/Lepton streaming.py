import queue
import threading
from PIL import Image
import io,ui
import socket
#https://github.com/gtrafimenkov/pycrc16
from crc16 import *
from datetime import *
import numpy as np
import console
from objc_util import *
from ctypes import *


AVAssetWriter=ObjCClass('AVAssetWriter')
AVAssetWriterInput=ObjCClass('AVAssetWriterInput')
AVAssetWriterInputPixelBufferAdaptor=ObjCClass('AVAssetWriterInputPixelBufferAdaptor')

CMTimeValue=c_int64
CMTimeScale=c_int32
CMTimeFlags=c_uint32
CMTimeEpoch=c_int64
class CMTime(Structure):
	_fields_=[('value',CMTimeValue),
	('timescale',CMTimeScale),
	('flags',CMTimeFlags),
	('epoch',CMTimeEpoch)]

kCMTimeZero=CMTime.in_dll(c,'kCMTimeZero')

kCVPixelFormatType_8IndexedGray_WhiteIsZero=0x028
kCVPixelFormatType_32ARGB=0x020

#Lepton resolution 
L_W=160
L_H=120

# buffers used to record the video
px_buff=c_uint8*(L_H*L_W)
px_buff_ARGB=c_uint8*(4*L_H*L_W)

CMTimeMake=c.CMTimeMake
CMTimeMake.restype=CMTime
CMTimeMake.argtypes=[c_int64,c_int32]

CVPixelBufferCreateWithBytes=c.CVPixelBufferCreateWithBytes
CVPixelBufferCreateWithBytes.restype=c_uint32
CVPixelBufferCreateWithBytes.argtypes=[c_void_p,c_int16,c_int16,c_int16,c_void_p,c_int16,c_void_p,c_void_p,c_void_p,c_void_p]

#t-linear default resolution
TLINEAR_RES=0.01

# min max temperature (Celcius) of the scene, only for initialisation , only for RAD/t-linear
T_MIN=0
T_MAX=100

#packet & segment sizes
PAC_SIZE=164
SEG_SIZE=PAC_SIZE*60

#expected frame rate = 9
FPS=9

HOST='192.168.4.1'
PORT=7677

#for debug
tab=[]
lframe=0
lseg=0
pframe=0

#used for video recording. rotation-> swap between L_W and L_H
videoSettings={'AVVideoCodecKey':'avc1','AVVideoWidthKey':L_H,'AVVideoHeightKey':L_W}

vW=None 


#handler - video recording
def handler_func(_block,_p):
	global vW
	print('completed')
	print('status (2=OK)',vW.status())
	print('error',vW.error())



class lepton_view(ui.View):
	def __init__(self,scale,v_format):
		
		self.v_format=v_format
		
		self.is_recording=False
		self.video_i=0
		
		self.set_mode()
			
		self.background_color='black'
		
		#image frame calculation according to the scale / zoom factor
		self.w,self.h=ui.get_screen_size()
		self.scale=scale
		self.calculate_frame()
		self.zoom_l=[1,1.5,2,2.5,3]
		self.zoom_l.append(self.w/L_H)
		
		#initialisation of the image view
		self.img_view=ui.ImageView(frame=(self.img_x,self.img_y,self.img_w,self.img_h),image=None)
		self.img_view.border_width=1
		self.img_view.border_color='blue'
		self.add_subview(self.img_view)
		
		# button set-up : the first one for the screenshots,  the second one for the zoom, the third one for the video recording
		xb=(self.w-60*3)/2
		self.screenshot=self.set_button(xb,self.h-60,'screenshot',ui.Image('typw:Camera'))
		self.zoom=self.set_button(xb+60,self.h-60,'zoom',ui.Image('typw:Zoom_In'))
		self.v_rec=self.set_button(xb+60*2,self.h-60,'v_rec',ui.Image('iow:record_32'))
		
		self.add_subview(self.screenshot)
		self.add_subview(self.zoom)
		self.add_subview(self.v_rec)
		
		self.screenshot_i=0
		
		
		# label /message set-up : bad crc (usually around 25%), queue size (should be near 0 if the frame calculation is faster than the udp), frame per second (fps, should be at 9 , at least outside US)
		xb=(self.w-60*2)/2
		
		self.crc_label=self.draw_Label('bad CRC: --',xb,14,'blue')
		self.add_subview(self.crc_label)
		
		self.q_size=self.draw_Label('qsize: --',xb,31,'blue')
		self.add_subview(self.q_size)
		
		self.fps_label=self.draw_Label('fps: --',xb,48,'blue')
		self.add_subview(self.fps_label)
		
		self.fps=None
		self.fps_t=None
		
		self.crc=0
		
		#specific initialisation sequence in rad/tlinear mode
		if self.v_format=="RGB":
			self.init_tlinear()
			
		
		#FIFO queue initialisation. Used between the segment receiption function & frame/segment handling function
		self.q=queue.Queue()
		
		
		# queue related to the video recording
		self.q_v=queue.Queue()
		
		#current segment number 
		self.seg_nr=None
		#segment/frame completion (if = 4, means that a frame is completed)
		self.seg_done=0
		#image "buffer" 
		self.img=Image.new(self.v_format, (L_W,L_H))
		self.px=self.img.load()
		#storage of the last completed image
		self.img_data=None
	
		# socket used to receive the segments. UDP
		self.udp_receive_sock = socket.socket(family=socket.AF_INET, type=socket.SOCK_DGRAM)
		#self.udp_receive_sock.settimeout(80)
		self.udp_receive_sock.bind(('0.0.0.0', 7674))
		
		self.is_listening=True
		self.is_streaming=True
		
		#two threads: 1) for receiption of the segments 2) for handling of the segments
		self.listener_thread=threading.Thread(target=self.listen_socket)
		self.listener_thread.start()
		self.seg_thread=threading.Thread(target=self.handle_queue)
		self.seg_thread.start()

		
	def set_mode(self):
		s = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM)
		
		s.settimeout(4)
		try:
			s.connect((HOST, PORT))
		except socket.timeout:
			print('can not connect')
			s.close()
			return False
		except OSError as e:
			print('exception',e)
			return False
		
		s.settimeout(0)
		s.send(self.v_format.encode())
		
		s.settimeout(5)
		try:
			data=s.recv(1024)
			s.close()
		except socket.timeout:
			print('no ack')
			s.close()
			return False
			#errno 54
	
		if data.decode()!='OK':
			print('error')
			return False
		else:
			return True

			
	def init_video_rec(self):
		global vW
		
		if self.v_format=='L':
			self.raw_data=px_buff()
			self.imgBPR=L_H
			self.imgT=kCVPixelFormatType_8IndexedGray_WhiteIsZero
		else:
			self.raw_data=px_buff_ARGB()
			self.imgBPR=4*L_H
			self.imgT=kCVPixelFormatType_32ARGB
		
		if self.video_i<10:
			filename='vid'+str('0')+str(self.video_i)+'.mp4'
		else:
			filename='vid'+str(self.video_i)+'.mp4'
		self.video_i+=1
		
		_error=c_void_p()
		self.videoWriter = AVAssetWriter.assetWriterWithURL_fileType_error_(nsurl(filename),'com.apple.quicktime-movie',_error)
		
		if _error.value!=None:
			return False
			
		vW=self.videoWriter
		
		self.videoWriterInput = AVAssetWriterInput.assetWriterInputWithMediaType_outputSettings_('vide',ns(videoSettings)) 
		self.adaptor=AVAssetWriterInputPixelBufferAdaptor.assetWriterInputPixelBufferAdaptorWithAssetWriterInput_sourcePixelBufferAttributes_(self.videoWriterInput,None)
		self.videoWriter.addInput(self.videoWriterInput)
		r=self.videoWriter.startWriting()
		r2=self.videoWriter.status()
		if r and r2==1:
			self.videoWriter.startSessionAtSourceTime_(kCMTimeZero,argtypes=[CMTime],restype=None)
			self.video_b=False
			return True
		else:
			return False
		
			
	def init_tlinear(self):
		#temperature label , only in rad/tlinear
		xb=(self.w-60*2)/2
		self.t_label=self.draw_Label('T: --',xb,65,'blue')
		self.add_subview(self.t_label)
		
		#rad/t-linear initialisation of the min max temperatures. Not used in AGC mode
		self.t_min=65535
		self.t_max=0
		Tmin=T_MIN+273.15
		Tmax=T_MAX+273.15
		#initial temperature range & minimum
		self.t_range=int(Tmax/TLINEAR_RES-Tmin/TLINEAR_RES)
		self.tmin=int(Tmin/TLINEAR_RES)
		#c_array_t : temperature buffer. array_t : temperature array once a frame is completed
		self.c_array_t=np.zeros((L_W,L_H))
		self.array_t=None
		
		#touch location
		self.t_t=ui.ImageView(frame=(0,0,10,10),image=ui.Image('emj:White_Circle'))
		
		
	def calculate_frame(self):
		self.img_x=(self.w-L_H*self.scale)/2
		self.img_y=(self.h-L_W*self.scale)/2
		self.img_w=self.scale*L_H
		self.img_h=self.scale*L_W
		
		
		
	def set_button(self,x,y,name,img):
		button = ui.Button(frame=(x,y,60,60),  name=name)
		#button.background_color = (0, 0, 0, 0.5)
		button.tint_color = 'white'
		button.border_width=0.5
		button.border_color='white'
		#button.title = ''
		button.image=img
		#button.image.with_rendering_mode(ui.RENDERING_MODE_AUTOMATIC)
		button.action = self.button_tapped
		button.alignment = ui.ALIGN_CENTER
		return button
		
	def button_tapped(self,sender):
		#actions related to the buttons: screenshot & zoom
		if sender.name=='screenshot':
			if self.img_data!=None:
				if self.screenshot_i<10:
					name='screenshot'+str('0')+str(self.screenshot_i)+'.jpg'
				else:
					name='screenshot'+str(self.screenshot_i)+'.jpg'
				f=open(name,'wb')
				f.write(self.img_data)
				f.close()
				self.screenshot_i+=1
		elif sender.name=='zoom':
			if self.scale in self.zoom_l:
				j=self.zoom_l.index(self.scale)
				j=(j+1) % len(self.zoom_l)
				self.scale=self.zoom_l[j]
			else:
				self.scale=1
			self.calculate_frame()
			self.img_view.frame=(self.img_x,self.img_y,self.img_w,self.img_h)
		elif sender.name=='v_rec':
			if self.is_recording==False:
				if self.init_video_rec():
					self.v_rec.image=ui.Image('iow:stop_32')
					self.is_recording=True
					self.video_thread=threading.Thread(target=self.handle_queue_v)
					self.video_thread.start()
					
			else:
				self.v_rec.image=ui.Image('iow:record_32')
				self.is_recording=False
				self.close_video()
				
			
			
			
	def draw_Label(self,text,x,y,color):
		classTxt=ui.Label(frame=(x,y,70,20))
		classTxt.text_color=color
		classTxt.text=text
		classTxt.alignment=ui.ALIGN_CENTER
		classTxt.border_color=color
		classTxt.border_width=2
		classTxt.background_color='#cccccc'
		#classTxt.number_of_lines=20
		classTxt.font=('HelveticaNeue-Light',10)
		#classTxt.size_to_fit()
		return classTxt
		
		
	def touch_began(self,touch):
		# rad / t-linear only : get the temperature of a given pixel
		if self.v_format=="RGB" and self.array_t!=None:
			x,y=touch.location
			if (self.img_x<=x<=self.img_x+self.img_w) and (self.img_y<=y<=self.img_y+self.img_h):
				Xp=int((x-self.img_x)/self.img_w*L_H)
				Yp=int((y-self.img_y)/self.img_h*L_W)
				X=Yp
				Y=L_H-Xp
				self.t_label.text='T: '+str(int(self.array_t[X,Y]))+' C'
				self.t_t.center=(x,y)
				self.add_subview(self.t_t)
				
	def touch_ended(self,touch):
		if self.v_format=='RGB':
			if self.t_t.superview!=None:
				self.remove_subview(self.t_t)
			
			
					
	
	def listen_socket(self):
		#segment receiption 
		print('starting listening\n')
		while (self.is_listening==True):
			try:
				(data,address)=self.udp_receive_sock.recvfrom(SEG_SIZE)
				self.q.put(data)
			except socket.timeout:
				#not used as no timeout is specified
				print('timeout')
			except OSError as e:
				print('exception',e)
				self.is_listening=False
		



	def handle_queue(self):
		#segment handling
		print('starting streaming\n')
		while (self.is_streaming==True):
			try:
				data=self.q.get()
				self.handle_data(data)
				self.q.task_done()
				
			except queue.Empty:
				#not used 
				print('empty')
			#except OSError as e:
				#print('exception',e)
				
				
	def handle_data(self,data):
		global lframe,lseg,pframe
		#main function that handles the packets/segments
		j=0
		while j<60:
			msb=data[0+j*PAC_SIZE]
			lsb=data[1+j*PAC_SIZE]
			if msb & 0xF==0:
				if lsb==0:
					self.seg_nr=None
				if self.seg_nr==None:
					#looks for the segment nr
					pos20=j*PAC_SIZE+(20-lsb)*PAC_SIZE
					if (lsb<20 and pos20<SEG_SIZE) or (lsb>20 and pos20>=0) or (lsb==20):
						self.seg_nr=data[pos20]
						self.seg_nr=self.seg_nr >> 4
						if self.seg_nr not in [1,2,3,4]:
							self.seg_nr=None
					else:
						lseg+=1
				if self.seg_nr!=None:
					pframe+=1
					#gets the color
					y=(self.seg_nr-1)*30+(lsb // 2)
					for k in range(0,80):
						x=(lsb % 2)*80+k
						self.px[x,y]=self.get_color_and_t(data[4+j*PAC_SIZE+2*k:6+j*PAC_SIZE+2*k],x,y)
						
						#in agc mode = 
						#self.px[x,y]=data[5+j*PAC_SIZE+k*2]
					
					# crc check	
					crc1=(data[2+j*PAC_SIZE] << 8) | data[3+j*PAC_SIZE]
					c_p=bytearray(data[0+j*PAC_SIZE:0+j*PAC_SIZE+PAC_SIZE])
					c_p[2]=c_p[3]=0
					crc2=crc16xmodem(c_p)
					if crc1!=crc2:
						self.crc+=1
					
					if lsb==59 and self.seg_done==self.seg_nr-1:
						#segment completion follow-up
						self.seg_done=self.seg_nr
				if self.seg_done==4:
					#a frame is achieved
					self.img=self.img.rotate(-90)
					with io.BytesIO() as bIO:
						self.img.save(bIO, 'JPEG')
						self.img_data=bIO.getvalue()
						img_ui = ui.Image.from_data(self.img_data)	
					# image view update	
					self.img_view.image=img_ui
					# temp array update  & t range (rad/t linear only/)
					if self.v_format=="RGB":
						self.update_t_range()
					if self.is_recording:
						self.put_video_frame()
					# re initialisation of the img buffer
					self.img = Image.new(self.v_format, (L_W,L_H))
					self.px=self.img.load()
					self.seg_done=0
	
					# label updates
					
					self.crc_label.text='bad crc: '+str(round(self.crc/(60*4)*100))+' %'
					self.crc=0
					self.q_size.text='qsize: '+str(self.q.qsize())
					if self.fps_t!=None:
						new_t=datetime.now()
						self.fps=1/self.diff_time(self.fps_t,new_t)
						self.fps_label.text='fps: '+str(round(self.fps))
						self.fps_t=new_t
						
					else:
						self.fps_t=datetime.now()
			else:
				if (msb & 0xF)==0xF:
					lframe+=1
						
			j+=1
				
	
	def put_video_frame(self):
		# this function is necessary to be consistent with the supported core video formats 
		px=self.img.load()
		if self.v_format=='L':
			#kCVPixelFormatType_8IndexedGray_WhiteIsZero
			for i in range(0,L_H):
				for j in range(0,L_W):
					self.raw_data[i+j*L_H]=255-px[i,j]
		else:
			#kCVPixelFormatType_32ARGB
			for i in range(0,L_H):
				for j in range(0,L_W):
					r,g,b=px[i,j]
					self.raw_data[4*i+j*L_H*4]=255
					self.raw_data[4*i+j*L_H*4+1]=r
					self.raw_data[4*i+j*L_H*4+2]=g
					self.raw_data[4*i+j*L_H*4+3]=b
		t=datetime.now()
		self.q_v.put((self.raw_data,t))
		
		
		
	def handle_queue_v(self):
		#video frame handling
		print('starting writing video\n')
		while (self.is_recording==True):
			try:
				data=self.q_v.get()
				self.video_processing(data)
				self.q_v.task_done()
				
			except queue.Empty:
				#not used 
				print('q_v empty')
			#except OSError as e:
				#print('exception',e)
		
		
	def video_processing(self,raw_data):
		data,t=raw_data
		if self.video_b==False:
			self.video_b=True
			self.video_t0=t
			n=0
		else:
			delta=t-self.video_t0
			n=round((delta.microseconds/1000000+delta.seconds)*(3*FPS))
		p=c_uint64()
		r=CVPixelBufferCreateWithBytes(None,L_H,L_W, self.imgT,pointer(data),self.imgBPR,None,None,None,byref(p))
		_buffer=c_void_p(p.value)
		flag=False
		while not flag:
			if self.adaptor.assetWriterInput().readyForMoreMediaData():
				self.adaptor.appendPixelBuffer_withPresentationTime_(_buffer,CMTimeMake(n,3*FPS),argtypes=[c_void_p,CMTime],restype=c_bool)
				flag=True
			else:
				self.smart_sleep(0.025)
		
		
	def update_t_range(self):
		# in RAD/t linear mode, update the temperature range according to the min max temperatures measured on the scene
		Tmax=self.t_max
		Tmin=self.t_min
		offset=0.05*(Tmax-Tmin)
		self.t_range=int(Tmax-Tmin+offset)
		self.tmin=int(Tmin-offset/2)
		self.t_max=0
		self.t_min=65535
		self.array_t=np.array(self.c_array_t)
		self.c_array_t=np.zeros((L_W,L_H))
		
		
	def get_color_and_t(self,data,x,y):
		if self.v_format=="L":
			return(data[1])
		else:
			t=(data[0] << 8) | data[1]
			if t>self.t_max:
				self.t_max=t
			if t<self.t_min:
				self.t_min=t
			
			self.c_array_t[x,y]=t*TLINEAR_RES-273.15
			return self.grey_to_RGB(t-self.tmin,self.t_range)
		
	
	def grey_to_RGB(self,v,N):
		# grey to rgb conversion. v: between 0 and N. N : range/max. v=0 blue, v=N/4 cyan v=N/2 green v=3N/4 yellow v=N red
		if v<N/4:
			b=255
		elif v<N/2:
			b=(-0xFF/(N/4)*v+2*0xFF)
		else:
			b=0
	
		if v>3*N/4:
			r=255
		elif v>N/2:
			r=0xFF/(N/4)*v-2*0xFF
		else:
			r=0
		
		if v<N/4:
			g=0xFF/(N/4)*v
		elif v>3*N/4:
			g=-0xFF/(N/4)*v+4*0xFF
		else:
			g=255
			
		return (int(r),int(g),int(b))
		
	
	
	def diff_time(self,start_time,new_time):
		diff = (new_time - start_time).seconds + ((new_time - start_time).microseconds / 1000000.0)
		return diff
		
		
	def smart_sleep(self, timeout):
		start_time = datetime.now()
		new_time = datetime.now()
		diff = (new_time - start_time).seconds + ((new_time - start_time).microseconds / 1000000.0)
		while (diff < timeout):
			new_time = datetime.now()
			diff = (new_time - start_time).seconds + ((new_time - start_time).microseconds / 1000000.0)
			
	
	
			
					
	def close_video(self):
		self.videoWriterInput.markAsFinished()
		handler = ObjCBlock(handler_func, restype=None, argtypes=[c_void_p,c_void_p])
		retain_global(handler)
		self.videoWriter.finishWritingWithCompletionHandler_(handler)
		
	
																																	
	def release_view(self):
		self.is_listening=False
		self.is_streaming=False
		if self.is_recording:
			self.is_recording=False
			self.close_video()
		self.udp_receive_sock.close()
		print('queue size',self.q.qsize(),'\n')
		print(lframe,lseg,pframe)
		
	
		
c=console.alert('Lepton thermal camera','Mode','AGC - 8 bit grayscale','Radiometry / TLinear - RGB')
if c==1:
	m='L'
else:
	m='RGB'
	
	

v=lepton_view(1,m)
v.present('fullscreen',hide_title_bar=True)
v.wait_modal()
v.release_view()











	








	

	
	
	
	
	







