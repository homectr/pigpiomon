#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import threading
import paho.mqtt.client as mqtt
import time, ssl, random
import datetime
import configparser
import sys, getopt
import pigpio

LOG_FATAL = 0
LOG_ERROR = 1
LOG_WARN  = 2
LOG_INFO  = 3
LOG_DEBUG = 4

# client, user and device details
serverUrl   = "localhost"
username    = "<<username>>"
password    = "<<password>>"

clientId    = "pyGPIOmon"
deviceName  = "PyGPIO Monitor"
LOGFILE     = "./py-gpio-monitor.log"
LOG_LEVEL   = LOG_INFO
gpios       = []
configFile  = './py-gpio-monitor.ini'

def cli_help():
  print('Usage: '+sys.argv[0]+' -c <configfile> -g <gpios> -v <verbose level> -l <logfile>')
  print()
  print('  -c | --config: ini-style configuration file, default is '+configFile)
  print('  -g | --gpios: comma separated list of gpios to monitor')
  print('  -v | --verbose: 0-fatal, 1-error, 2-warning, 3-info, 4-debug')
  print('  -l | --logfile: log file name,default is '+LOGFILE)  
  print()
  print('Example: '+sys.argv[0]+' -c /etc/monitor.ini -g13,24,25 -v 2 -l /var/log/monitor.log')

def getOptions(argv):
  try:
    opts, args = getopt.getopt(argv,"hg:c:v:l:",["config=","verbose=", "logfile=","gpios="])
  except getopt.GetoptError:
    print("Command line argument error")
    help()
    sys.exit(2)

  for opt, arg in opts:
    if opt == '-h':
      help()
      sys.exit()
    elif opt in ("-c", "--config"):
      configFile = arg
    elif opt in ("-v", "--verbose"):
      LOG_LEVEL = int(arg)
    elif opt in ("-l", "--logfile"):
      LOGFILE = arg
    elif opt in ("-g", "--gpios"):
      for g in arg.split(','):
        gpios.append(int(g))

def getConfig(cf):
  print('Using configuration file ', cf)
  config = configparser.ConfigParser()
  config.read(cf)

  try:
    secServer = config['mqtt']
  except KeyError:
    print('Error: configuration file is not correct or missing')
    exit(1)

  serverUrl = secServer.get('url','localhost')
  username = secServer.get('username')
  password = secServer.get('password')
  clientId = secServer.get('clientid','pyGPIOmon')  

class PyGPIOmon(threading.Thread):
  def __init__(self, clientId, name, mqttClient, gpios, pi, logFile):
    threading.Thread.__init__(self)
    self.clientId = clientId
    self.name = name
    self.running = True
    self.mqtt = mqttClient # mqtt client
    self.gpios = gpios # array of gpio numbers to monitor
    self.logF = logFile # log file name
    self.pi = pi  # pigpio instance
    self.f = 0  # logfile
    self.mqtt.on_message = self.on_message
    self.mqtt.on_publish = self.on_publish
    self.mqtt.on_connect = self.on_mqtt_connect
    self.mqtt_reconnect = 0
    self.cbs = [] # array of gpio callbacks
    self.ticks = {}

  def stop(self):
    for c in self.cbs:
      c.cancel()
  
  def run(self):
    print("Starting " + self.name)
    print("Opening log file " + self.logF)

    try:
      self.f = open(self.logF, "a")
    except FileNotFoundError:
      print("Error opening log file.")
      exit(1)

    self.logI("*** PyGPIOmon Starting")
    self.logI("Starting MQTT client")
    self.mqtt.loop_start()
    self.mqtt.subscribe("cmd/"+self.clientId)

    print("Connecting to gpios")
    # register callback function for interrupts
    tick=pi.get_current_tick()
    for g in self.gpios:
      self.cbs.append(pi.callback(g, pigpio.EITHER_EDGE, self.cbf))
      self.ticks[g]=tick
    
    print("Starting monitoring loop")
    while self.running:
      if self.mqtt_reconnect > 0:
        self.logW("MQTT Reconnecting...")
        self.mqtt.reconnect()
      else:
        time.sleep(10)

  def logW(self, msg):
    self.log(msg, level=LOG_WARN)

  def logE(self, msg):
    self.log(msg, level=LOG_ERROR)

  def logD(self, msg):
    self.log(msg, level=LOG_DEBUG)

  def logI(self, msg):
    self.log(msg, level=LOG_INFO)  
  
  def log(self, msg, level=LOG_WARN):
    if level > LOG_LEVEL: 
      return
    l = ["F","E","W","I","D"]
    ts = datetime.datetime.now().isoformat(timespec="seconds")
    print(ts + "  " + l[level] + "  " + msg)
    self.f.write(ts + "  " + l[level] + "  " + msg + "\n")
   
  # display all incoming messages
  def on_message(self, userdata, message):
    self.logI("MQTT received msg="+str(message.payload))
  
  def on_publish(self, userdata, mid):
    self.receivedMessages.append(mid)
  
  def on_mqtt_connect(self, client, userdata, flags, rc):
    self.mqtt_connected = rc
    self.mqtt_reconnect = 0
    if rc != 0:
      self.logE("MQTT connection returned result="+rc)
      self.mqtt_reconnect += 1
      if self.mqtt_reconnect > 12: self.mqtt_reconnect = 12
      self.mqtt_reconnect_delay = 2**self.mqtt_reconnect
    else:
      self.logI("Connected to MQTT broker.")
  
  def on_mqtt_disconnect(self, client, userdata, rc):
    self.mqtt_reconnect = 1
    if rc != 0:
      self.logE("MQTT unexpected disconnection.")
      self.mqtt_reconnect = True
      self.mqtt_reconnect_delay = 10
  
  # publish a message
  def publish(self, topic, message, waitForAck = False):
    mid = self.mqtt.publish(topic, message, 1)[1]
    if (waitForAck):
        while mid not in self.receivedMessages:
            time.sleep(0.25)

  # callback for interrupts
  def cbf(GPIO, level, tick):
    if tick - 50000 > self.ticks[GPIO]: # debounce 50ms
      self.ticks[GPIO] = tick
      if level == pigpio.RISING_EDGE:
        self.publish('GPIO:'+str(GPIO),"ON")
      if level == pigpio.FALLING_EDGE:
        self.publish('GPIO:'+str(GPIO),"OFF")


#-------------------------------------------------------
getOptions(sys.argv[1:])
getConfig(configFile)

if len(gpios) == 0:
  print("Error: no gpios specified")
  cli_help()
  exit(1)

print("Going to monitor gpios=", gpios)

pi = pigpio.pi()

if not pi.connected:
  print("Error: Failed connecting to pigpiod. Installed and running?")
  exit(3)

# connect the client to MQTT broker and register a device
print("Creating MQTT client for",serverUrl)
mqtt = mqtt.Client(clientId)
mqtt.username_pw_set(username, password)
mqtt.connect_async(serverUrl)

print("Creating PyGPIOmon device as",clientId)
mon = PyGPIOmon(clientId, deviceName, mqtt, gpios, pi, LOGFILE)
mon.start()

try:
  time.sleep(30)
  while True:
    print("PyGPIOmon Alive")
    time.sleep(900)
except KeyboardInterrupt:
  print("\nTidying up")
  mon.stop()

pi.stop()
